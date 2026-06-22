"""
src/api/main.py

FastAPI application entry point for the CPG Analytics platform.

Start locally:
    uvicorn src.api.main:app --reload --port 8000

Or via Docker Compose:
    docker compose --profile full up
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from loguru import logger

from src.api.routes import (
    ask,
    database,
    dq_reports,
    forecast,
    generate,
    health,
    ingest,
    insights,
    quality,
    summary,
)
from src.common.db import ping


@asynccontextmanager
async def lifespan(app: FastAPI):
    connected = ping()
    if connected:
        logger.info("API ready — database reachable")
    else:
        logger.warning("API starting — database NOT reachable; /health will report degraded")
    yield
    logger.info("API shutdown")


app = FastAPI(
    title="CPG Analytics API",
    version="1.0.0",
    description=(
        "Revenue forecasting, data quality monitoring, AI insights, "
        "and natural-language Q&A for CPG sales data."
    ),
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


# Route registration
app.include_router(health.router, tags=["Health"])
app.include_router(ingest.router, tags=["Ingestion"])
app.include_router(summary.router, tags=["Analytics"])
app.include_router(quality.router, tags=["Analytics"])
app.include_router(forecast.router, tags=["Analytics"])
app.include_router(insights.router, tags=["AI"])
app.include_router(ask.router, tags=["AI"])
app.include_router(dq_reports.router, tags=["Data Quality"])
app.include_router(generate.router, tags=["Operations"])
app.include_router(database.router, tags=["Database"])
