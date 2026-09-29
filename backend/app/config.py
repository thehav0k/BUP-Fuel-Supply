from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    simulator_url: str = "http://localhost:8000"
    prediction_url: str = "http://localhost:8002"
    database_url: str = ""  # empty disables persistence (tests, local runs)
    poll_interval_s: float = 2.0
    sim_timeout_s: float = 2.0
    sim_get_attempts: int = 3
    breaker_failures: int = 5
    breaker_reset_s: float = 10.0
    prediction_timeout_s: float = 1.0
    default_mode: str = "manual"
    rec_expiry_ticks: int = 4
    horizon_ticks: int = 48
    degraded_after_s: float = 5.0
    grafana_url: str = "http://localhost:3001/d/fuel-ops/fuel-supply-operations"
    enable_demo_controls: bool = True
    enable_sse: bool = True
    enable_sync: bool = True
    hybrid_min_confidence: float = 0.8
    hybrid_max_risk: float = 0.7
    llm_explanations: bool = False
    llm_api_key: str = ""
    llm_base_url: str = "https://api.cerebras.ai/v1"
    llm_model: str = "qwen-3.8-27b"
    llm_timeout_s: float = 1.5

    @classmethod
    def from_env(cls) -> Settings:
        d = cls()
        return cls(
            simulator_url=os.getenv("SIMULATOR_URL", d.simulator_url).rstrip("/"),
            prediction_url=os.getenv("PREDICTION_URL", d.prediction_url).rstrip("/"),
            database_url=os.getenv("DATABASE_URL", d.database_url),
            poll_interval_s=_float("POLL_INTERVAL_S", d.poll_interval_s),
            sim_timeout_s=_float("SIM_TIMEOUT_S", d.sim_timeout_s),
            prediction_timeout_s=_float("PREDICTION_TIMEOUT_S", d.prediction_timeout_s),
            default_mode=os.getenv("DEFAULT_MODE", d.default_mode),
            rec_expiry_ticks=int(_float("REC_EXPIRY_TICKS", d.rec_expiry_ticks)),
            grafana_url=os.getenv("GRAFANA_URL", d.grafana_url),
            enable_demo_controls=_bool("ENABLE_DEMO_CONTROLS", d.enable_demo_controls),
            enable_sse=_bool("ENABLE_SSE", d.enable_sse),
            enable_sync=_bool("ENABLE_SYNC", d.enable_sync),
            hybrid_min_confidence=_float("HYBRID_MIN_CONFIDENCE", d.hybrid_min_confidence),
            hybrid_max_risk=_float("HYBRID_MAX_RISK", d.hybrid_max_risk),
            llm_explanations=_bool("LLM_EXPLANATIONS", bool(os.getenv("CEREBRAS_API_KEY"))),
            llm_api_key=os.getenv("CEREBRAS_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", d.llm_base_url).rstrip("/"),
            llm_model=os.getenv("LLM_MODEL", d.llm_model),
            llm_timeout_s=_float("LLM_TIMEOUT_S", d.llm_timeout_s),
        )
