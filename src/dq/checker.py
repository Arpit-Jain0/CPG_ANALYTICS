"""
src/dq/checker.py

Pre-ingestion data quality checks.

Three checks run in order on every sheet before it is handed to the ingestion
pipeline:

  1. Duplicate rows    — all-column exact matches; keep first occurrence
  2. PK uniqueness     — duplicate values in the designated primary-key column;
                         keep first occurrence, remove subsequent ones
  3. Datatype rules    — per-column type validation (numeric / positive_numeric /
                         datetime); rows that violate ANY rule are removed

Rejected rows are written to a single CSV report in quality_reports_dir so
every fault is visible and auditable without touching the clean dataset.

Report filename format:
    {YYYYMMDD_HHMMSS}_{source_file_stem}_{sheet_name}_dq_report.csv
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

# ── Private helpers ───────────────────────────────────────────────────────────


def _invalid_mask(series: pd.Series, rule: str) -> pd.Series:
    """Return a boolean mask: True for rows that violate the given type rule."""
    if rule == "numeric":
        coerced = pd.to_numeric(series, errors="coerce")
        return coerced.isna() & series.notna()

    if rule == "positive_numeric":
        coerced = pd.to_numeric(series, errors="coerce")
        type_bad = coerced.isna() & series.notna()
        val_bad = coerced.notna() & (coerced <= 0)
        return type_bad | val_bad

    if rule == "datetime":
        parsed = pd.to_datetime(series, errors="coerce")
        return parsed.isna() & series.notna()

    logger.warning("DQ: unknown rule '{}' — skipping column", rule)
    return pd.Series(False, index=series.index)


def _write_report(rejected: pd.DataFrame, quality_dir: Path, filename: str) -> None:
    """Persist rejected rows to a CSV inside quality_dir."""
    quality_dir.mkdir(parents=True, exist_ok=True)
    out_path = quality_dir / filename
    rejected.to_csv(out_path, index=False, encoding="utf-8")
    logger.info("    DQ report → {} ({} row(s))", out_path.name, len(rejected))


# ── Public API ────────────────────────────────────────────────────────────────


def run_dq_checks(
    df: pd.DataFrame,
    pk_column: str | None,
    datatype_rules: dict[str, str],
    source_file: str,
    sheet_name: str,
    quality_dir: Path,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Run all three DQ checks and route rejected rows to a quality report.

    Parameters
    ----------
    df            : cleaned DataFrame (post clean_dataframe, pre apply_sheet_config)
    pk_column     : column name that is the logical primary key (may be None)
    datatype_rules: mapping of column_name → rule string
    source_file   : original filename — used in the report and its filename
    sheet_name    : worksheet name — used in the report and its filename
    quality_dir   : directory where the CSV report is written

    Returns
    -------
    (clean_df, rejected_df, counts)
        clean_df     : DataFrame with all violating rows removed
        rejected_df  : DataFrame of all rejected rows (with _dq_* columns);
                       empty DataFrame if no violations found
        counts       : {"DUPLICATE_ROW": n, "PK_DUPLICATE": n, "DATATYPE_VIOLATION": n}
                       Only populated keys had violations.
    """
    counts: dict[str, int] = {}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_stem = Path(source_file).stem.replace(" ", "_")
    sheet_slug = sheet_name.replace(" ", "_")
    report_name = f"{ts}_{file_stem}_{sheet_slug}_dq_report.csv"
    all_rejected: list[pd.DataFrame] = []

    # ── 1. Duplicate rows ─────────────────────────────────────────────────────
    dup_mask = df.duplicated(keep="first")
    n_dup = int(dup_mask.sum())
    if n_dup:
        rej = df[dup_mask].copy()
        rej["_dq_issue"] = "DUPLICATE_ROW"
        rej["_dq_detail"] = "exact copy of an earlier row in this batch"
        rej["_dq_action"] = "REMOVED"
        rej["_dq_source_file"] = source_file
        rej["_dq_sheet"] = sheet_name
        all_rejected.append(rej)
        df = df[~dup_mask].reset_index(drop=True)
        counts["DUPLICATE_ROW"] = n_dup
        logger.info("    DQ duplicate rows: {} removed", n_dup)

    # ── 2. PK uniqueness ──────────────────────────────────────────────────────
    if pk_column:
        if pk_column in df.columns:
            pk_dup_mask = df.duplicated(subset=[pk_column], keep="first")
            n_pk = int(pk_dup_mask.sum())
            if n_pk:
                rej = df[pk_dup_mask].copy()
                rej["_dq_issue"] = "PK_DUPLICATE"
                rej["_dq_detail"] = (
                    "duplicate value in '"
                    + pk_column
                    + "': "
                    + df.loc[pk_dup_mask, pk_column].astype(str).values
                )
                rej["_dq_action"] = "REMOVED"
                rej["_dq_source_file"] = source_file
                rej["_dq_sheet"] = sheet_name
                all_rejected.append(rej)
                df = df[~pk_dup_mask].reset_index(drop=True)
                counts["PK_DUPLICATE"] = n_pk
                logger.info(
                    "    DQ PK duplicates: {} removed (pk_column='{}')",
                    n_pk,
                    pk_column,
                )
        else:
            logger.warning(
                "    DQ pk_column '{}' not found in sheet '{}' — PK check skipped",
                pk_column,
                sheet_name,
            )

    # ── 3. Datatype validation ────────────────────────────────────────────────
    if datatype_rules:
        # detail_list[i] accumulates all rule violations for row i
        detail_list: list[str] = [""] * len(df)
        any_invalid = pd.Series(False, index=df.index)

        for col, rule in datatype_rules.items():
            if col not in df.columns:
                logger.warning(
                    "    DQ datatype rule column '{}' not in sheet '{}' — skipped",
                    col,
                    sheet_name,
                )
                continue

            col_bad = _invalid_mask(df[col], rule)
            # Since df.index is a clean RangeIndex after reset_index, the index
            # value equals the positional offset — safe to use directly.
            for idx in col_bad[col_bad].index:
                detail_list[idx] += f"{col}({rule}) "

            any_invalid |= col_bad

        n_dt = int(any_invalid.sum())
        if n_dt:
            rej = df[any_invalid].copy()
            rej["_dq_issue"] = "DATATYPE_VIOLATION"
            rej["_dq_detail"] = [detail_list[i].strip() for i in rej.index]
            rej["_dq_action"] = "REMOVED"
            rej["_dq_source_file"] = source_file
            rej["_dq_sheet"] = sheet_name
            all_rejected.append(rej)
            df = df[~any_invalid].reset_index(drop=True)
            counts["DATATYPE_VIOLATION"] = n_dt
            logger.info("    DQ datatype violations: {} removed", n_dt)

    # ── Write combined report ─────────────────────────────────────────────────
    if all_rejected:
        combined = pd.concat(all_rejected, ignore_index=True)
        _write_report(combined, quality_dir, report_name)
    else:
        combined = pd.DataFrame()
        logger.debug("    DQ: no violations found in sheet '{}'", sheet_name)

    return df, combined, counts
