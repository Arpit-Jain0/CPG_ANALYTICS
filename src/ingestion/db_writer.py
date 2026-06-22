"""
src/ingestion/db_writer.py

Postgres persistence for the three-layer data architecture:

  raw.*      — raw rows landed as TEXT before any cleaning or DQ filtering
  curated.*  — DQ-passed, typed rows ready for analytics
  error.*    — rows rejected by the pre-ingestion DQ gate

Also handles archiving the original xlsx files to data/archive/{YYYY-MM-DD}/.

All DB writes use the SQLAlchemy engine from src.common.db.  If the engine is
not reachable (DB down) the functions log a warning and return 0 so the rest
of the pipeline (CSV write) still succeeds.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

# ── Archive ───────────────────────────────────────────────────────────────────


def archive_file(fpath: Path, archive_root: Path) -> Path:
    """
    Copy *fpath* to ``archive_root/{YYYY-MM-DD}/{filename}`` before processing.

    Returns the destination path.  If the file already exists in the archive
    folder for today it is overwritten (same-day re-run of the same file).
    """
    dest_dir = archive_root / str(date.today())
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fpath.name
    shutil.copy2(fpath, dest)
    logger.info("  Archived {} → {}", fpath.name, dest)
    return dest


# ── Internal helpers ──────────────────────────────────────────────────────────


def _split_table(table_ref: str) -> tuple[str, str]:
    """'raw.pos_transactions'  →  ('raw', 'pos_transactions')"""
    parts = table_ref.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"table_ref must be 'schema.table', got: {table_ref!r}")
    return parts[0], parts[1]


def _meta_cols(
    source_file: str,
    sheet_name: str,
    load_batch_id: int | None,
) -> dict:
    return {
        "_source_file": source_file,
        "_sheet_name": sheet_name,
        "_load_batch_id": load_batch_id,
        "_ingested_at": datetime.now(UTC),
    }


# ── RAW layer ─────────────────────────────────────────────────────────────────


def write_raw(
    df: pd.DataFrame,
    raw_table: str,
    source_file: str,
    sheet_name: str,
    load_batch_id: int | None,
    engine: Engine,
) -> int:
    """
    Write *df* to the specified raw.* table as TEXT rows.

    The DataFrame is expected to be the result of read_workbook() with column
    names lowercased — no DQ filtering, no type coercion beyond basic
    normalisation.  All business columns are cast to str before insert so the
    raw table retains the original string representation of every value.

    Returns the number of rows written, or 0 on DB error.
    """
    if df.empty:
        return 0

    schema, table = _split_table(raw_table)

    # Cast all business columns to string (preserve raw values exactly)
    df_raw = df.copy().astype(object)
    for col in df_raw.columns:
        df_raw[col] = df_raw[col].where(df_raw[col].notna(), other=None)
        df_raw[col] = df_raw[col].apply(lambda v: str(v) if v is not None else None)

    # Inject metadata
    for k, v in _meta_cols(source_file, sheet_name, load_batch_id).items():
        df_raw[k] = v

    # Keep only columns that exist in the target table (handles extra Excel cols)
    try:
        with engine.connect() as conn:
            existing = pd.read_sql(
                text(f"SELECT * FROM {schema}.{table} LIMIT 0"),
                conn,
            ).columns.tolist()
    except Exception as exc:
        logger.warning("write_raw: could not read {}.{} schema — {}", schema, table, exc)
        return 0

    meta_keys = set(_meta_cols(source_file, sheet_name, load_batch_id).keys())
    biz_cols = [c for c in existing if c not in meta_keys and not c.startswith("_raw_id")]
    meta_cols_order = [c for c in existing if c in meta_keys]

    # Align: keep only known columns, fill missing business cols with None
    final_cols = biz_cols + meta_cols_order
    for col in biz_cols:
        if col not in df_raw.columns:
            df_raw[col] = None
    df_insert = df_raw[[c for c in final_cols if c in df_raw.columns]]

    try:
        df_insert.to_sql(
            table,
            engine,
            schema=schema,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=500,
        )
        logger.info("  RAW  {}.{}: inserted {} row(s)", schema, table, len(df_insert))
        return len(df_insert)
    except Exception as exc:
        logger.warning("write_raw {}.{} failed — {}", schema, table, exc)
        return 0


# ── ERROR layer ───────────────────────────────────────────────────────────────


def write_error(
    rejected: pd.DataFrame,
    source_file: str,
    sheet_name: str,
    load_batch_id: int | None,
    engine: Engine,
) -> int:
    """
    Write DQ-rejected rows to ``error.dq_rejected_rows``.

    The rejected DataFrame already carries ``_dq_issue``, ``_dq_detail``,
    ``_dq_action`` columns from the DQ checker.  All other columns are
    serialised to JSONB via the ``row_data`` column.

    Returns the number of rows written, or 0 on DB error.
    """
    if rejected.empty:
        return 0

    dq_cols = {"_dq_issue", "_dq_detail", "_dq_action", "_dq_source_file", "_dq_sheet"}
    biz_cols = [c for c in rejected.columns if c not in dq_cols]

    rows = []
    for _, row in rejected.iterrows():
        row_dict = {c: (None if pd.isna(row[c]) else str(row[c])) for c in biz_cols}
        rows.append(
            {
                "_source_file": source_file,
                "_sheet_name": sheet_name,
                "_load_batch_id": load_batch_id,
                "_ingested_at": datetime.now(UTC),
                "dq_issue": row.get("_dq_issue"),
                "dq_detail": str(row.get("_dq_detail", "")),
                "dq_action": row.get("_dq_action"),
                "row_data": json.dumps(row_dict),
            }
        )

    df_err = pd.DataFrame(rows)

    try:
        df_err.to_sql(
            "dq_rejected_rows",
            engine,
            schema="error",
            if_exists="append",
            index=False,
            method="multi",
            chunksize=500,
        )
        logger.info("  ERROR error.dq_rejected_rows: inserted {} row(s)", len(df_err))
        return len(df_err)
    except Exception as exc:
        logger.warning("write_error failed — {}", exc)
        return 0


# ── CURATED layer ─────────────────────────────────────────────────────────────


def write_curated(
    df: pd.DataFrame,
    curated_table: str,
    write_mode: str,
    pk_column: str | None,
    load_batch_id: int | None,
    engine: Engine,
) -> int:
    """
    Write DQ-passed, mapped rows to the specified curated.* table.

    write_mode == "overwrite"
        TRUNCATE the target table then INSERT all rows.  Used for dimension
        tables that are fully replaced on each historical load.

    write_mode == "append"
        INSERT rows with ON CONFLICT (pk_column) DO NOTHING so re-running the
        same file is idempotent (no duplicate rows).

    Returns the number of rows inserted, or 0 on DB error.
    """
    if df.empty:
        return 0

    schema, table = _split_table(curated_table)

    # Inject audit metadata
    df_cur = df.copy()
    df_cur["_load_batch_id"] = load_batch_id
    df_cur["_ingested_at"] = datetime.now(UTC)

    # Align to target table columns
    try:
        with engine.connect() as conn:
            target_cols = pd.read_sql(
                text(f"SELECT * FROM {schema}.{table} LIMIT 0"),
                conn,
            ).columns.tolist()
    except Exception as exc:
        logger.warning("write_curated: could not read {}.{} schema — {}", schema, table, exc)
        return 0

    # Drop auto-generated cols (_update_id etc.), keep only what we can supply
    skip = {
        c for c in target_cols if c.endswith("_id") and c.startswith("_") and c != "_load_batch_id"
    }
    insert_cols = [c for c in target_cols if c not in skip]

    for col in insert_cols:
        if col not in df_cur.columns:
            df_cur[col] = None
    df_insert = df_cur[[c for c in insert_cols if c in df_cur.columns]]

    try:
        with engine.begin() as conn:
            if write_mode == "overwrite":
                conn.execute(text(f"TRUNCATE TABLE {schema}.{table}"))
                logger.info("  CURATED {}.{}: truncated", schema, table)

            if write_mode == "append" and pk_column and pk_column in df_insert.columns:
                # Idempotent upsert: skip rows whose PK already exists
                _upsert_ignore(df_insert, schema, table, pk_column, conn)
            else:
                df_insert.to_sql(
                    table,
                    conn,
                    schema=schema,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=500,
                )

        logger.info(
            "  CURATED {}.{}: {} row(s) written ({})", schema, table, len(df_insert), write_mode
        )
        return len(df_insert)
    except Exception as exc:
        logger.warning("write_curated {}.{} failed — {}", schema, table, exc)
        return 0


def _upsert_ignore(
    df: pd.DataFrame,
    schema: str,
    table: str,
    pk_col: str,
    conn,
) -> None:
    """
    INSERT rows using ON CONFLICT (pk_col) DO NOTHING.
    Falls back to plain INSERT if pk_col is not a unique/PK constraint
    (e.g. curated.product_updates uses a surrogate _update_id, not sku).
    """
    if df.empty:
        return

    cols = list(df.columns)
    placeholders = ", ".join([f":{c}" for c in cols])
    col_names = ", ".join([f'"{c}"' for c in cols])
    sql = text(
        f'INSERT INTO {schema}."{table}" ({col_names}) VALUES ({placeholders}) '
        f'ON CONFLICT ("{pk_col}") DO NOTHING'
    )

    records = df.where(df.notna(), other=None).to_dict(orient="records")
    try:
        # Savepoint so a constraint mismatch doesn't abort the whole transaction
        conn.execute(text("SAVEPOINT _upsert_sp"))
        conn.execute(sql, records)
        conn.execute(text("RELEASE SAVEPOINT _upsert_sp"))
    except Exception:
        # pk_col is not a unique/PK constraint (e.g. curated.product_updates uses
        # surrogate _update_id — multiple rows per sku are valid there)
        conn.execute(text("ROLLBACK TO SAVEPOINT _upsert_sp"))
        df.to_sql(
            table,
            conn,
            schema=schema,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=500,
        )
