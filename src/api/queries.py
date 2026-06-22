"""
src/api/queries.py

Data-access helpers for the API layer.  All heavy lifting lives here so
routes stay thin.

All revenue data is read from curated Postgres tables.
Quality logs, load_batch, and forecast_results are also read from Postgres.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.common.config import get_settings
from src.common.db import get_session
from src.ingestion.config_loader import load_config  # still needed for quality_reports_dir

# ── Root resolution ───────────────────────────────────────────────────────────

# Resolves from src/api/ → src/ → project root
_APP_ROOT: Path = Path(__file__).resolve().parents[2]


def app_root() -> Path:
    return _APP_ROOT


def quality_reports_dir() -> Path:
    cfg_path = _APP_ROOT / get_settings().ingestion_config
    icfg = load_config(cfg_path)
    return _APP_ROOT / icfg.settings.quality_reports_dir


# ── DB loaders ────────────────────────────────────────────────────────────────


def _load_sales() -> pd.DataFrame:
    """
    Return sales joined with category + brand (dim_product) and region (dim_store)
    from curated Postgres tables.
    """
    sql = text("""
        SELECT
            st.transaction_ts,
            st.store_id,
            st.sku,
            st.quantity,
            st.unit_price,
            COALESCE(st.revenue, st.unit_price * st.quantity) AS revenue,
            dp.category,
            dp.brand,
            ds.region
        FROM curated.sales_transactions st
        LEFT JOIN curated.dim_product dp ON dp.sku = st.sku
        LEFT JOIN curated.dim_store   ds ON ds.store_id = st.store_id
        WHERE st.transaction_ts IS NOT NULL
          AND (
              st.revenue IS NOT NULL
              OR (st.unit_price IS NOT NULL AND st.quantity IS NOT NULL)
          )
    """)
    with get_session() as session:
        result = session.execute(sql)
        df = pd.DataFrame(result.fetchall(), columns=list(result.keys()))

    df["ds"] = pd.to_datetime(df["transaction_ts"], errors="coerce").dt.normalize()
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    return df.dropna(subset=["ds", "revenue"])


# ── Summary queries ───────────────────────────────────────────────────────────


def get_revenue_kpis(
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    df = _load_sales()

    if start_date:
        df = df[df["ds"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["ds"] <= pd.Timestamp(end_date)]

    by_cat = df.groupby("category")["revenue"].sum().sort_values(ascending=False)
    by_reg = df.groupby("region")["revenue"].sum().sort_values(ascending=False)

    return {
        "total_revenue": round(float(df["revenue"].sum()), 2),
        "top_category": str(by_cat.index[0]) if len(by_cat) else "N/A",
        "top_region": str(by_reg.index[0]) if len(by_reg) else "N/A",
        "transaction_count": int(len(df)),
        "by_category": [
            {"category": str(k), "revenue": round(float(v), 2)} for k, v in by_cat.items()
        ],
        "by_region": [{"region": str(k), "revenue": round(float(v), 2)} for k, v in by_reg.items()],
        "start_date": start_date,
        "end_date": end_date,
    }


# ── Quality queries (DB) ──────────────────────────────────────────────────────


def get_quality_summary() -> dict[str, Any]:
    with get_session() as session:
        issues = session.execute(text("""
                SELECT issue_type, count(*) AS cnt
                FROM data_quality_log
                GROUP BY issue_type
                ORDER BY cnt DESC
            """)).fetchall()

        actions = session.execute(text("""
                SELECT action_taken, count(*) AS cnt
                FROM data_quality_log
                GROUP BY action_taken
                ORDER BY cnt DESC
            """)).fetchall()

        total = session.execute(text("SELECT count(*) FROM data_quality_log")).scalar()

        total_batches = session.execute(text("SELECT count(*) FROM load_batch")).scalar()

        latest = session.execute(text("""
                SELECT load_batch_id, load_type, source_file,
                       rows_in, inserted, deduped, rejected,
                       repaired, flagged, late_arriving
                FROM load_batch
                ORDER BY load_batch_id DESC
                LIMIT 1
            """)).fetchone()

    return {
        "total_issues": int(total or 0),
        "by_issue_type": [{"issue_type": r[0], "count": int(r[1])} for r in issues],
        "by_action_taken": [{"action_taken": r[0], "count": int(r[1])} for r in actions],
        "total_batches": int(total_batches or 0),
        "latest_batch": dict(latest._mapping) if latest else None,
    }


# ── Forecast queries (DB) ─────────────────────────────────────────────────────


def get_forecast_rows(
    category: str | None,
    region: str | None,
    horizon: int,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: dict[str, Any] = {"horizon": horizon}

    if category:
        clauses.append("category = :category")
        params["category"] = category
    if region:
        clauses.append("region = :region")
        params["region"] = region

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with get_session() as session:
        # Latest run_date for this filter
        run_row = session.execute(
            text(f"SELECT MAX(run_date) FROM forecast_results {where}"),
            params,
        ).scalar()

        if run_row is None:
            return {
                "run_date": None,
                "model_version": None,
                "points": [],
            }

        params["run_date"] = run_row

        run_filter = ("AND" if where else "WHERE") + " run_date = :run_date"

        version = session.execute(
            text(f"SELECT model_version FROM forecast_results {where} {run_filter} LIMIT 1"),
            params,
        ).scalar()

        rows = session.execute(
            text(f"""
                SELECT target_date, predicted_revenue, yhat_lower, yhat_upper
                FROM forecast_results
                {where} {run_filter}
                ORDER BY target_date
                LIMIT :horizon
            """),
            params,
        ).fetchall()

    return {
        "run_date": run_row,
        "model_version": version,
        "points": [
            {
                "target_date": r[0],
                "predicted_revenue": float(r[1]),
                "yhat_lower": float(r[2]) if r[2] is not None else None,
                "yhat_upper": float(r[3]) if r[3] is not None else None,
            }
            for r in rows
        ],
    }


# ── Ingest helpers ────────────────────────────────────────────────────────────


def run_ingest(mode: str) -> dict[str, Any]:
    """
    Run the ingestion pipeline filtered to the given mode, write a load_batch
    record to the DB, and return audit stats.

    mode = "historical" → groups whose dir contains "historical"
    mode = "incremental" → groups whose dir contains "incremental"
    """
    from src.ingestion.config_loader import IngestionConfig, load_config
    from src.ingestion.pipeline import run_pipeline

    root = app_root()
    cfg_path = root / get_settings().ingestion_config
    config = load_config(cfg_path)

    # Filter groups by mode keyword in their dir path
    matched = [g for g in config.file_groups if mode in g.dir.lower() and g.enabled]
    if not matched:
        return {
            "files_processed": 0,
            "inserted": 0,
            "load_batch_id": None,
        }

    filtered = IngestionConfig(settings=config.settings, file_groups=matched)

    # File count (before running so spinner covers the wait)
    files_processed = sum(
        len(list((root / g.dir).glob(g.file_pattern))) for g in matched if (root / g.dir).exists()
    )

    # Write load_batch record BEFORE pipeline so pipeline rows can reference it
    load_batch_id: int | None = None
    started_at = datetime.utcnow()
    try:
        with get_session() as session:
            lb_result = session.execute(
                text("""
                    INSERT INTO load_batch
                        (load_type, source_file, started_at, inserted)
                    VALUES
                        (:load_type, :source_file, :started_at, 0)
                    RETURNING load_batch_id
                """),
                {
                    "load_type": mode.upper(),
                    "source_file": f"{len(matched)} group(s)",
                    "started_at": started_at,
                },
            )
            load_batch_id = lb_result.scalar()
    except Exception:
        pass  # DB write failure does not abort the ingest

    # Run the pipeline — returns actual row counts
    pipeline_stats = run_pipeline(root, filtered, load_batch_id=load_batch_id)
    finished_at = datetime.utcnow()

    inserted = pipeline_stats.get("inserted", 0)
    raw_rows = pipeline_stats.get("raw_rows", 0)
    error_rows = pipeline_stats.get("error_rows", 0)

    # Update load_batch with final counts
    if load_batch_id is not None:
        try:
            with get_session() as session:
                session.execute(
                    text("""
                        UPDATE load_batch
                        SET finished_at = :finished_at,
                            inserted    = :inserted,
                            rejected    = :rejected,
                            rows_in     = :rows_in
                        WHERE load_batch_id = :id
                    """),
                    {
                        "finished_at": finished_at,
                        "inserted": inserted,
                        "rejected": error_rows,
                        "rows_in": raw_rows,
                        "id": load_batch_id,
                    },
                )
        except Exception:
            pass

    return {
        "files_processed": pipeline_stats.get("files_processed", files_processed),
        "inserted": inserted,
        "raw_rows": raw_rows,
        "error_rows": error_rows,
        "load_batch_id": load_batch_id,
    }


# ── Bounded context for /ask ──────────────────────────────────────────────────


def build_bounded_context() -> str:
    """
    Build a compact, pre-aggregated text context for the LLM.
    Never sends raw transaction rows — only summary statistics.
    """
    df = _load_sales()

    total_rev = df["revenue"].sum()
    date_min = df["ds"].min().date() if not df["ds"].isna().all() else "N/A"
    date_max = df["ds"].max().date() if not df["ds"].isna().all() else "N/A"

    by_cat = df.groupby("category")["revenue"].sum().sort_values(ascending=False)
    by_reg = df.groupby("region")["revenue"].sum().sort_values(ascending=False)

    # Monthly revenue (last 12 months)
    df["ym"] = df["ds"].dt.to_period("M")
    by_month = df.groupby("ym")["revenue"].sum().sort_index().tail(12)

    # Month-over-month growth for category top-movers
    df_m = df.groupby(["ym", "category"])["revenue"].sum().reset_index()
    df_m["ym_str"] = df_m["ym"].astype(str)
    recent_months = sorted(df_m["ym_str"].unique())[-2:]
    movers: list[str] = []
    if len(recent_months) == 2:
        prev_m, curr_m = recent_months
        prev = df_m[df_m["ym_str"] == prev_m].set_index("category")["revenue"]
        curr = df_m[df_m["ym_str"] == curr_m].set_index("category")["revenue"]
        growth = ((curr - prev) / prev.replace(0, float("nan"))).dropna().sort_values()
        for cat, pct in growth.items():
            movers.append(f"  {cat}: {pct:+.1%}")

    # Quality summary from DB
    try:
        qs = get_quality_summary()
        quality_text = (
            f"Total quality issues logged: {qs['total_issues']}\n"
            f"Total ingestion batches: {qs['total_batches']}"
        )
    except Exception:
        quality_text = "Quality data unavailable"

    # Forecast summary from DB
    try:
        with get_session() as session:
            fc_count = session.execute(text("SELECT count(*) FROM forecast_results")).scalar()
            fc_max = session.execute(text("SELECT MAX(target_date) FROM forecast_results")).scalar()
        forecast_text = f"Forecast rows in DB: {fc_count} (latest target: {fc_max})"
    except Exception:
        forecast_text = "Forecast data unavailable"

    lines = [
        "=== CPG Analytics — Data Summary Context ===",
        f"Date range : {date_min} to {date_max}",
        f"Total revenue : ${total_rev:,.2f}",
        f"Total transactions : {len(df):,}",
        "",
        "Revenue by Category:",
        *[f"  {k}: ${v:,.2f} ({v/total_rev:.1%})" for k, v in by_cat.items()],
        "",
        "Revenue by Region:",
        *[f"  {k}: ${v:,.2f} ({v/total_rev:.1%})" for k, v in by_reg.items()],
        "",
        "Monthly Revenue (last 12 months):",
        *[f"  {str(period)}: ${val:,.2f}" for period, val in by_month.items()],
        "",
        "Category Revenue Growth (latest MoM):",
        *(movers if movers else ["  N/A"]),
        "",
        f"Data Quality: {quality_text}",
        f"Forecasting: {forecast_text}",
        "=" * 46,
    ]
    return "\n".join(lines)


def get_product_performance(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Top products by revenue with brand + category enrichment from curated tables."""
    df = _load_sales()
    if start_date:
        df = df[df["ds"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["ds"] <= pd.Timestamp(end_date)]

    # brand and category come from the _load_sales() JOIN with curated.dim_product
    prods = df[["sku", "brand", "category"]].drop_duplicates("sku")

    by_sku = (
        df.groupby("sku")
        .agg(revenue=("revenue", "sum"), transactions=("revenue", "count"))
        .reset_index()
    )
    by_sku = by_sku.merge(prods, on="sku", how="left")
    by_sku = by_sku.sort_values("revenue", ascending=False).head(limit)

    return [
        {
            "sku": str(row["sku"]),
            "brand": str(row["brand"]) if pd.notna(row.get("brand")) else None,
            "category": str(row["category"]) if pd.notna(row.get("category")) else None,
            "revenue": round(float(row["revenue"]), 2),
            "transactions": int(row["transactions"]),
        }
        for _, row in by_sku.iterrows()
    ]


def get_dq_report_files() -> list[dict[str, Any]]:
    """Scan quality_reports/ and return metadata for every *_dq_report.csv."""
    from datetime import datetime as _dt

    qdir = quality_reports_dir()
    if not qdir.exists():
        return []

    result: list[dict[str, Any]] = []
    for fpath in sorted(qdir.glob("*_dq_report.csv"), reverse=True):
        try:
            df = pd.read_csv(fpath)
            by_issue: dict[str, int] = {}
            if "_dq_issue" in df.columns:
                by_issue = {k: int(v) for k, v in df["_dq_issue"].value_counts().items()}

            src_file = (
                str(df["_dq_source_file"].iloc[0])
                if "_dq_source_file" in df.columns and len(df) > 0
                else None
            )
            sheet = (
                str(df["_dq_sheet"].iloc[0]) if "_dq_sheet" in df.columns and len(df) > 0 else None
            )

            # Parse timestamp from filename prefix YYYYMMDD_HHMMSS_*
            ts_str: str | None = None
            try:
                parts = fpath.stem.split("_")
                if len(parts) >= 2 and len(parts[0]) == 8 and len(parts[1]) == 6:
                    ts_str = _dt.strptime(parts[0] + parts[1], "%Y%m%d%H%M%S").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
            except Exception:
                pass

            result.append(
                {
                    "filename": fpath.name,
                    "total_rejected": len(df),
                    "by_issue": by_issue,
                    "source_file": src_file,
                    "sheet": sheet,
                    "report_ts": ts_str,
                }
            )
        except Exception:
            pass
    return result


def get_dq_report_detail(filename: str) -> list[dict[str, Any]]:
    """Return rows from one DQ report CSV, guarding against path traversal."""
    qdir = quality_reports_dir()
    fpath = (qdir / filename).resolve()
    if not str(fpath).startswith(str(qdir.resolve())):
        raise ValueError("Invalid filename")
    if not fpath.exists():
        raise FileNotFoundError(f"DQ report not found: {filename}")
    df = pd.read_csv(fpath)
    return df.where(pd.notna(df), other=None).to_dict(orient="records")


def get_insights_aggregates() -> dict[str, Any]:
    """Return the aggregates needed for /insights (separate from bounded context)."""
    df = _load_sales()

    total = df["revenue"].sum()
    by_cat = df.groupby("category")["revenue"].sum().sort_values(ascending=False)
    by_reg = df.groupby("region")["revenue"].sum().sort_values(ascending=False)

    return {
        "total_revenue": round(float(total), 2),
        "by_category": [
            {"category": str(k), "revenue": round(float(v), 2)} for k, v in by_cat.items()
        ],
        "by_region": [{"region": str(k), "revenue": round(float(v), 2)} for k, v in by_reg.items()],
    }
