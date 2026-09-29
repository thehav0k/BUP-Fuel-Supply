from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import demo, router
from app.config import Settings
from app.explain import Explainer
from app.logs import setup_logging
from app.runtime import Runtime


def create_app(settings: Settings | None = None, **runtime_kwargs: object) -> FastAPI:
    settings = settings or Settings.from_env()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        explainer = None
        if settings.llm_explanations and settings.llm_api_key:
            explainer = Explainer(settings.llm_api_key, base_url=settings.llm_base_url, model=settings.llm_model,
                                  timeout=settings.llm_timeout_s)
        runtime = Runtime(settings, explainer=explainer, **runtime_kwargs)  # type: ignore[arg-type]
        app.state.runtime = runtime
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()
            if explainer:
                await explainer.close()

    app = FastAPI(title="Fuel Supply Operations Platform", version="1.0.0", lifespan=lifespan)
    app.include_router(router)
    app.include_router(demo)
    Instrumentator(excluded_handlers=["/metrics"]).instrument(app).expose(app, include_in_schema=False)
    return app


app = create_app()
