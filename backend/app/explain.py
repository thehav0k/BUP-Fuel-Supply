"""Optional LLM explanations (PRD 9.3) via Cerebras' OpenAI-compatible chat API.

The LLM only rewrites numbers the engine already computed into two sentences. The template text stays when the
call fails, times out (1.5 s) or returns nothing, and explanations run in the background so they never delay
a decision cycle.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.logs import event

log = logging.getLogger("app.explain")

SYSTEM = (
    "You explain fuel shipment recommendations to an operations operator. Write exactly two short sentences: "
    "first the risk (station, fuel, when it runs out or how low it gets, demand rate, any spike), then the action "
    "(quantity, source depot, route, arrival time, why a backup route or cap applies) and the risk change. "
    "Use only the facts and numbers given; do not invent any. Plain text, no markdown."
)


class Explainer:
    def __init__(self, api_key: str, *, base_url: str, model: str, timeout: float = 1.5,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.model = model
        self.timeout = timeout
        self.http = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self.ok = 0
        self.failed = 0
        self._tasks: set[asyncio.Task[None]] = set()

    async def close(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await self.http.aclose()

    def schedule(self, recs: list[Any], on_done: Any) -> None:
        """Explain in the background; `on_done(rec)` persists a rec whose text was replaced."""
        for rec in recs:
            task = asyncio.create_task(self._explain(rec, on_done))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _explain(self, rec: Any, on_done: Any) -> None:
        text = await self.explain(rec.facts)
        if text and rec.status in ("OPEN", "SUBMITTING", "SUBMITTED"):
            rec.reason = text
            rec.reason_source = "llm"
            on_done(rec)

    async def explain(self, facts: dict[str, Any]) -> str | None:
        body = {
            "model": self.model,
            "max_completion_tokens": 600,
            "reasoning_effort": "low",
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(facts, default=str)},
            ],
        }
        try:
            resp = await asyncio.wait_for(self.http.post("/chat/completions", json=body), timeout=self.timeout)
            resp.raise_for_status()
            text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
        except (httpx.HTTPError, TimeoutError, KeyError, IndexError, ValueError) as exc:
            self.failed += 1
            event(log, "llm_explanation_failed", logging.INFO, error=type(exc).__name__)
            return None
        if not text or len(text) > 600:
            self.failed += 1
            return None
        self.ok += 1
        return " ".join(text.split())
