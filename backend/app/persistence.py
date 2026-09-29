"""Write-behind persistence to Postgres.

The API and the engine never wait on the database: writes go into a queue and a worker applies them in order,
retrying with backoff while the database is down. On startup, recent recommendations, decisions and settings are
loaded back so the decision log survives restarts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, Integer, String, Text, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.logs import event
from app.metrics import DB_PENDING, DB_UP

log = logging.getLogger("app.db")
Op = Callable[[AsyncSession], Awaitable[None]]


class Base(DeclarativeBase):
    pass


class DemandObservation(Base):
    __tablename__ = "demand_observations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # simulator row id
    station_id: Mapped[str] = mapped_column(String(64), index=True)
    fuel_type: Mapped[str] = mapped_column(String(16))
    tick: Mapped[int] = mapped_column(Integer, index=True)
    sim_time: Mapped[str] = mapped_column(String(40))
    demand_liters: Mapped[float] = mapped_column(Float)
    served_liters: Mapped[float] = mapped_column(Float)
    unmet_liters: Mapped[float] = mapped_column(Float)


class RecommendationRow(Base):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    created_tick: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    station_id: Mapped[str] = mapped_column(String(64))
    fuel: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float)
    route_id: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DecisionRow(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    recommendation_id: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(16))
    tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    station_id: Mapped[str] = mapped_column(String(64))
    fuel: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float)
    route_id: Mapped[str] = mapped_column(String(64))
    allocation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allocation_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SettingRow(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class Persistence:
    def __init__(self, url: str, *, max_queue: int = 50_000):
        self.url = url
        self.enabled = bool(url)
        self.engine: AsyncEngine | None = None
        self.session: async_sessionmaker[AsyncSession] | None = None
        self.queue: asyncio.Queue[tuple[str, Op]] = asyncio.Queue(maxsize=max_queue)
        self.up = False
        self.ready = False
        self.last_ok_at: float | None = None
        self.last_error: str | None = None
        self.dropped = 0
        self._task: asyncio.Task[None] | None = None

    @property
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        return "up" if self.up else "down"

    async def connect(self, attempts: int = 1) -> bool:
        if not self.enabled:
            return False
        if self.engine is None:
            self.engine = create_async_engine(self.url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                                              connect_args=self._connect_args())
            self.session = async_sessionmaker(self.engine, expire_on_commit=False)
        for i in range(attempts):
            try:
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                self._mark(True)
                self.ready = True
                return True
            except Exception as exc:
                self._mark(False, exc)
                if i + 1 < attempts:
                    await asyncio.sleep(min(5.0, 0.5 * 2**i))
        return False

    def _connect_args(self) -> dict[str, Any]:
        return {"timeout": 3, "command_timeout": 5} if self.url.startswith("postgresql+asyncpg") else {}

    def _mark(self, ok: bool, exc: Exception | None = None) -> None:
        if ok != self.up:
            event(log, "db_up" if ok else "db_down", logging.INFO if ok else logging.WARNING,
                  error=None if exc is None else str(exc)[:200])
        self.up = ok
        DB_UP.set(1 if ok else 0)
        if ok:
            self.last_ok_at = time.time()
            self.last_error = None
        elif exc is not None:
            self.last_error = f"{type(exc).__name__}: {str(exc)[:160]}"

    def start(self) -> None:
        if self.enabled and self._task is None:
            self._task = asyncio.create_task(self._worker(), name="db-writer")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self.engine:
            await self.engine.dispose()

    def enqueue(self, name: str, op: Op) -> None:
        if not self.enabled:
            return
        try:
            self.queue.put_nowait((name, op))
        except asyncio.QueueFull:
            self.dropped += 1
        DB_PENDING.set(self.queue.qsize())

    async def _worker(self) -> None:
        backoff = 0.5
        while True:
            if not self.ready:
                if not await self.connect():
                    await asyncio.sleep(backoff)
                    backoff = min(10.0, backoff * 2)
                    continue
            _name, op = await self.queue.get()
            while True:
                try:
                    assert self.session is not None
                    async with self.session() as session, session.begin():
                        await op(session)
                    self._mark(True)
                    backoff = 0.5
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._mark(False, exc)
                    await asyncio.sleep(backoff)
                    backoff = min(10.0, backoff * 2)
            DB_PENDING.set(self.queue.qsize())

    # ------------------------------------------------------------------ writes

    def upsert_demand(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        values = [
            {k: r[k] for k in ("id", "station_id", "fuel_type", "tick", "sim_time", "demand_liters", "served_liters",
                               "unmet_liters")}
            for r in rows
        ]

        async def op(s: AsyncSession) -> None:
            for i in range(0, len(values), 500):
                stmt = pg_insert(DemandObservation).values(values[i : i + 500])
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={c: stmt.excluded[c] for c in ("station_id", "fuel_type", "tick", "sim_time",
                                                        "demand_liters", "served_liters", "unmet_liters")},
                )
                await s.execute(stmt)

        self.enqueue("demand", op)

    def clear_demand(self) -> None:
        async def op(s: AsyncSession) -> None:
            await s.execute(delete(DemandObservation))

        self.enqueue("clear_demand", op)

    def save_recommendation(self, rec: dict[str, Any], run_id: int) -> None:
        row = {
            "id": rec["id"], "run_id": run_id, "created_tick": rec["created_tick"], "status": rec["status"],
            "station_id": rec["station_id"], "fuel": rec["fuel"], "quantity": rec["quantity"],
            "route_id": rec["route_id"], "idempotency_key": rec["idempotency_key"], "fallback": rec["fallback"],
            "payload": rec, "updated_at": datetime.now(UTC),
        }

        async def op(s: AsyncSession) -> None:
            stmt = pg_insert(RecommendationRow).values(row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"], set_={k: stmt.excluded[k] for k in row if k != "id"}
            )
            await s.execute(stmt)

        self.enqueue("recommendation", op)

    def save_decision(self, decision: dict[str, Any], run_id: int) -> None:
        cols = ("id", "recommendation_id", "action", "actor", "tick", "station_id", "fuel", "quantity", "route_id",
                "allocation_id", "allocation_status", "failure_code", "failure_reason", "note")
        row = {k: decision.get(k) for k in cols}
        row["run_id"] = run_id
        row["created_at"] = _dt(decision["created_at"])

        async def op(s: AsyncSession) -> None:
            stmt = pg_insert(DecisionRow).values(row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"], set_={k: stmt.excluded[k] for k in row if k != "id"}
            )
            await s.execute(stmt)

        self.enqueue("decision", op)

    def save_setting(self, key: str, value: Any) -> None:
        async def op(s: AsyncSession) -> None:
            stmt = pg_insert(SettingRow).values(key=key, value=value)
            stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": stmt.excluded.value})
            await s.execute(stmt)

        self.enqueue("setting", op)

    # ------------------------------------------------------------------ reads (startup only)

    async def load_recent(self, limit: int = 300) -> dict[str, Any]:
        out: dict[str, Any] = {"recommendations": [], "decisions": [], "settings": {}, "run_id": 0}
        if not (self.enabled and self.ready and self.session):
            return out
        try:
            async with self.session() as s:
                recs = (await s.execute(
                    select(RecommendationRow).order_by(RecommendationRow.updated_at.desc()).limit(limit)
                )).scalars().all()
                decs = (await s.execute(
                    select(DecisionRow).order_by(DecisionRow.id.desc()).limit(limit)
                )).scalars().all()
                settings = (await s.execute(select(SettingRow))).scalars().all()
            out["recommendations"] = [dict(r.payload, _run_id=r.run_id) for r in recs]
            out["decisions"] = [
                {c.name: getattr(d, c.name) for c in DecisionRow.__table__.columns} for d in decs
            ]
            for d in out["decisions"]:
                d["created_at"] = d["created_at"].isoformat()
            out["settings"] = {r.key: r.value for r in settings}
            out["run_id"] = max([r.run_id for r in recs] + [d["run_id"] for d in out["decisions"]] + [0])
        except Exception as exc:
            self._mark(False, exc)
        return out
