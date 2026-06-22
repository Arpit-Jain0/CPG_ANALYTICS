"""
src/api/routes/dq_reports.py

Data-quality report browsing endpoints and product-level analytics.

GET /dq-reports              — list all *_dq_report.csv files with per-check counts
GET /dq-reports/{filename}   — rows from one report CSV
GET /products                — top products by revenue (with brand + category)
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Path, Query
from loguru import logger

from src.api.models import (
    DQReportDetailResponse,
    DQReportFileMeta,
    DQReportListResponse,
    ProductRevenue,
    ProductsResponse,
)
from src.api.queries import get_dq_report_detail, get_dq_report_files, get_product_performance

router = APIRouter()


@router.get("/dq-reports", response_model=DQReportListResponse)
def list_dq_reports() -> DQReportListResponse:
    """
    List every DQ violation report CSV written by the pre-ingestion checker.

    Each entry shows:
    - `filename` — the CSV file name (pass to /dq-reports/{filename} for full rows)
    - `total_rejected` — number of rows removed from the clean dataset
    - `by_issue` — breakdown by check type (DUPLICATE_ROW, PK_DUPLICATE, DATATYPE_VIOLATION)
    - `source_file` / `sheet` — which workbook + sheet generated this report
    - `report_ts` — when the check ran (parsed from the filename)
    """
    logger.info("GET /dq-reports")
    try:
        files = get_dq_report_files()
    except Exception as exc:
        logger.exception("DQ report list failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DQReportListResponse(
        reports=[DQReportFileMeta(**f) for f in files],
        total=len(files),
    )


@router.get("/dq-reports/{filename}", response_model=DQReportDetailResponse)
def dq_report_detail(
    filename: str = Path(description="DQ report CSV filename (from /dq-reports list)"),
) -> DQReportDetailResponse:
    """
    Return all rejected rows from a specific DQ report CSV.

    Each row carries the original data columns plus:
    - `_dq_issue` — which check caught it
    - `_dq_detail` — human-readable reason
    - `_dq_action` — always REMOVED
    - `_dq_source_file` / `_dq_sheet` — provenance
    """
    logger.info("GET /dq-reports/{}", filename)
    try:
        rows = get_dq_report_detail(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("DQ report detail failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DQReportDetailResponse(filename=filename, rows=rows, total=len(rows))


@router.get("/products", response_model=ProductsResponse)
def products(
    start_date: date | None = Query(default=None, description="Filter from this date"),
    end_date: date | None = Query(default=None, description="Filter to this date"),
    limit: int = Query(default=20, ge=1, le=100, description="Max products to return"),
) -> ProductsResponse:
    """
    Top products (SKUs) ranked by total revenue, enriched with brand and category.

    Optionally scoped to a date range via **start_date** / **end_date**.
    Requires ingestion to have run first.
    """
    logger.info("GET /products  start={} end={} limit={}", start_date, end_date, limit)
    try:
        data = get_product_performance(start_date, end_date, limit)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Downstream data not found — run ingestion first. ({exc})",
        ) from exc
    except Exception as exc:
        logger.exception("Products query failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ProductsResponse(
        products=[ProductRevenue(**p) for p in data],
        total=len(data),
    )
