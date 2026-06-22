"""Pydantic response models for all API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

# ── Health ────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    db_connected: bool
    version: str = "1.0.0"


# ── Ingest ────────────────────────────────────────────────────────────────────


class BatchStats(BaseModel):
    load_batch_id: int | None = None
    load_type: str
    source_file: str | None = None
    rows_in: int = 0
    inserted: int = 0
    deduped: int = 0
    rejected: int = 0
    repaired: int = 0
    flagged: int = 0
    late_arriving: int = 0


class IngestResponse(BaseModel):
    status: str  # "ok" | "error"
    mode: str
    files_processed: int
    batch: BatchStats


# ── Summary ───────────────────────────────────────────────────────────────────


class CategoryRevenue(BaseModel):
    category: str
    revenue: float


class RegionRevenue(BaseModel):
    region: str
    revenue: float


class SummaryResponse(BaseModel):
    total_revenue: float
    top_category: str
    top_region: str
    revenue_by_category: list[CategoryRevenue]
    revenue_by_region: list[RegionRevenue]
    transaction_count: int
    start_date: date | None = None
    end_date: date | None = None


# ── Quality ───────────────────────────────────────────────────────────────────


class QualityIssueCount(BaseModel):
    issue_type: str
    count: int


class QualityActionCount(BaseModel):
    action_taken: str
    count: int


class QualityResponse(BaseModel):
    total_issues: int
    by_issue_type: list[QualityIssueCount]
    by_action_taken: list[QualityActionCount]
    latest_batch: BatchStats | None = None
    total_batches: int = 0


# ── Forecast ──────────────────────────────────────────────────────────────────


class ForecastPoint(BaseModel):
    target_date: date
    predicted_revenue: float
    yhat_lower: float | None = None
    yhat_upper: float | None = None


class ForecastResponse(BaseModel):
    category: str | None = None
    region: str | None = None
    horizon: int
    run_date: date | None = None
    model_version: str | None = None
    points: list[ForecastPoint]


# ── AI / LLM ─────────────────────────────────────────────────────────────────


class InsightsResponse(BaseModel):
    summary: str
    llm_used: bool
    revenue_by_category: list[CategoryRevenue]
    revenue_by_region: list[RegionRevenue]


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    answer: str
    llm_used: bool
    context_preview: str  # first 300 chars of context, for transparency


# ── Products ──────────────────────────────────────────────────────────────────


class ProductRevenue(BaseModel):
    sku: str
    brand: str | None = None
    category: str | None = None
    revenue: float
    transactions: int


class ProductsResponse(BaseModel):
    products: list[ProductRevenue]
    total: int


# ── DQ Reports ────────────────────────────────────────────────────────────────


class DQReportFileMeta(BaseModel):
    filename: str
    total_rejected: int
    by_issue: dict[str, int]
    source_file: str | None = None
    sheet: str | None = None
    report_ts: str | None = None


class DQReportListResponse(BaseModel):
    reports: list[DQReportFileMeta]
    total: int


class DQReportDetailResponse(BaseModel):
    filename: str
    rows: list[dict[str, Any]]
    total: int


# ── Database Explorer ─────────────────────────────────────────────────────────


class TableInfo(BaseModel):
    schema_name: str
    table: str
    row_count: int


class SchemaInfo(BaseModel):
    schema_name: str
    tables: list[TableInfo]


class DBOverviewResponse(BaseModel):
    schemas: list[SchemaInfo]


class TableDataResponse(BaseModel):
    schema_name: str
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


# ── Batch Generation ──────────────────────────────────────────────────────────


class GenerateBatchResponse(BaseModel):
    status: str  # "created" | "exists"
    batch_type: str  # "pos" | "online"
    file: str  # filename (e.g. 2026-06-16_pos.xlsx)
    path: str  # absolute path on the server
    week_start: str  # ISO date of the Monday that starts the week
    rows: int  # rows written (0 if status == "exists")
    dq: dict[str, int]  # {issue_type: count} for injected DQ faults
