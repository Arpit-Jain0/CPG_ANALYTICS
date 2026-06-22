"""
src/api/routes/database.py

Endpoints for browsing the Postgres schema, table metadata, and row data.
Used by the UI "Database Explorer" page.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from sqlalchemy import text

from src.api.models import DBOverviewResponse, SchemaInfo, TableDataResponse, TableInfo
from src.common.db import engine

router = APIRouter(prefix="/db")

# Only expose these schemas — never let callers read pg_catalog etc.
_ALLOWED_SCHEMAS = {"raw", "curated", "error", "public"}


def _require_schema(schema: str) -> None:
    if schema not in _ALLOWED_SCHEMAS:
        raise HTTPException(
            status_code=400,
            detail=f"Schema '{schema}' not allowed. Choose from: {sorted(_ALLOWED_SCHEMAS)}",
        )


@router.get("/overview", response_model=DBOverviewResponse)
def db_overview() -> DBOverviewResponse:
    """
    Return all schemas with their tables and live row counts.
    Row counts come from pg_stat_user_tables (fast approximate count).
    """
    sql = text("""
        SELECT
            t.table_schema  AS schema_name,
            t.table_name    AS table_name,
            COALESCE(s.n_live_tup, 0) AS row_count
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s
               ON s.schemaname = t.table_schema
              AND s.relname    = t.table_name
        WHERE t.table_schema IN ('raw', 'curated', 'error', 'public')
          AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_schema, t.table_name
    """)

    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).mappings().all()
    except Exception as exc:
        logger.exception("db_overview query failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Group by schema
    schemas: dict[str, list[TableInfo]] = {}
    for r in rows:
        sname = r["schema_name"]
        if sname not in schemas:
            schemas[sname] = []
        schemas[sname].append(
            TableInfo(
                schema_name=sname,
                table=r["table_name"],
                row_count=int(r["row_count"]),
            )
        )

    schema_order = ["raw", "curated", "error", "public"]
    result = [
        SchemaInfo(schema_name=s, tables=schemas.get(s, [])) for s in schema_order if s in schemas
    ]
    return DBOverviewResponse(schemas=result)


@router.get("/table", response_model=TableDataResponse)
def db_table(
    schema: str = Query(..., description="Schema name (raw | curated | error | public)"),
    table: str = Query(..., description="Table name"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TableDataResponse:
    """
    Fetch rows from a specific schema.table with pagination.
    schema and table names are validated against an allowlist.
    """
    _require_schema(schema)

    # Validate table name against what actually exists — prevents SQL injection
    check_sql = text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = :schema AND table_name = :table AND table_type = 'BASE TABLE'
    """)
    try:
        with engine.connect() as conn:
            exists = conn.execute(check_sql, {"schema": schema, "table": table}).scalar()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not exists:
        raise HTTPException(status_code=404, detail=f"Table '{schema}.{table}' not found")

    # Safe to interpolate now — names are confirmed to exist in information_schema
    count_sql = text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
    data_sql = text(f'SELECT * FROM "{schema}"."{table}" LIMIT :limit OFFSET :offset')

    try:
        with engine.connect() as conn:
            total = conn.execute(count_sql).scalar() or 0
            result = conn.execute(data_sql, {"limit": limit, "offset": offset})
            columns = list(result.keys())
            rows = [dict(zip(columns, r, strict=False)) for r in result.fetchall()]
    except Exception as exc:
        logger.exception("db_table query failed for {}.{}", schema, table)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Convert non-serialisable types (datetime, Decimal) to str
    safe_rows = []
    for row in rows:
        safe_rows.append(
            {
                k: (str(v) if v is not None and not isinstance(v, (int, float, bool, str)) else v)
                for k, v in row.items()
            }
        )

    return TableDataResponse(
        schema_name=schema,
        table=table,
        columns=columns,
        rows=safe_rows,
        total=total,
        limit=limit,
        offset=offset,
    )
