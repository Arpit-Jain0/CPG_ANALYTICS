"""
src/ingestion/pipeline.py

Config-driven ingestion pipeline.

Flow per file group:
  1. Discover files via glob (dir + file_pattern from config)
  2. Read each .xlsx with robust ghost-sheet + header-row detection
  3. Clean the DataFrame (nulls, dates, numerics, whitespace)
  4. Apply column map and inject static columns
  5. Append or overwrite the target CSV in data/output/downstream/

Usage
-----
    python -m src.ingestion.pipeline [--root .] [--config config/ingestion.json]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.common.config import get_settings
from src.common.excel_io import read_workbook
from src.ingestion.config_loader import (
    FileGroup,
    IngestionConfig,
    PipelineSettings,
    SheetConfig,
    load_config,
)


# ── Edge-case cleaning ────────────────────────────────────────────────────────

def _try_parse_dates(series: pd.Series, formats: list[str]) -> pd.Series:
    """
    Attempt date parsing with each configured format string, then fall back to
    pandas' own inference.  Returns original series if nothing succeeds.
    """
    for fmt in formats:
        parsed = pd.to_datetime(series, format=fmt, errors="coerce")
        if parsed.notna().sum() >= series.notna().sum() * 0.5:
            return parsed
    # Generic fallback — handles Python datetime / Timestamp objects too
    return pd.to_datetime(series, errors="coerce")


def _try_numeric(series: pd.Series) -> pd.Series:
    """
    Strip common currency symbols and thousands separators, then try coercing
    to numeric.  Only replaces the column if > 50 % of non-null values parse
    successfully — keeps string IDs (TXN001, STORE001) untouched.
    """
    stripped = series.astype(str).str.replace(r"[$,€£¥\s]", "", regex=True)
    numeric = pd.to_numeric(stripped, errors="coerce")
    if numeric.notna().sum() >= series.notna().sum() * 0.5:
        return numeric
    return series


_DATE_KEYWORDS = ("_date", "_ts", "_at", "_time", "datetime", "date", "timestamp")
_ID_KEYWORDS   = ("_id", "_key", "order_id", "transaction_id", "campaign_id",
                   "promo_id", "store_id", "location_id")


def clean_dataframe(df: pd.DataFrame, settings: PipelineSettings) -> pd.DataFrame:
    """
    Standard edge-case handling applied to every sheet before writing:

    1. Normalise column names → lowercase + strip whitespace
    2. Replace null markers (configurable) with pd.NA
    3. Drop fully-empty rows
    4. Strip leading/trailing whitespace from string values
    5. Parse date-like columns (heuristic: column name contains date keyword)
    6. Coerce numeric strings (currency symbols, commas) — skips ID columns
    """
    # 1. Column names
    df.columns = [str(c).strip().lower() for c in df.columns]

    # 2. Null markers
    df = df.replace(settings.null_values, pd.NA)

    # 3. Drop all-null rows
    df = df.dropna(how="all").reset_index(drop=True)

    # 4. Strip string values
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

    # 5. Date parsing
    for col in df.columns:
        if any(kw in col for kw in _DATE_KEYWORDS):
            df[col] = _try_parse_dates(df[col], settings.date_formats)

    # 6. Numeric coercion (skip ID-like columns)
    for col in df.select_dtypes(include="object").columns:
        if not any(kw in col for kw in _ID_KEYWORDS):
            df[col] = _try_numeric(df[col])

    return df


# ── Column mapping + enrichment ───────────────────────────────────────────────

def apply_sheet_config(
    df: pd.DataFrame,
    sheet_cfg: SheetConfig,
    source_filename: str,
) -> pd.DataFrame:
    """
    Apply the sheet config's column_map, add_columns, and optional dedup.

    column_map
        When provided, only the listed source columns are kept and renamed.
        Unrecognised source columns are dropped without error.
        When absent, all columns pass through unchanged.

    add_columns
        Injects static columns; a value of null in the JSON means "use the
        source filename" at runtime.

    dedup_column
        In-batch deduplication on the named column (cross-run dedup is the
        downstream system's responsibility).
    """
    # Column map — lowercase the map keys to match post-clean column names
    if sheet_cfg.column_map:
        cmap = {k.lower(): v for k, v in sheet_cfg.column_map.items()}
        matched = {c: cmap[c] for c in df.columns if c in cmap}
        missing = [k for k in cmap if k not in df.columns]
        if missing:
            logger.warning("    column_map: source columns not found → {}", missing)
        df = df[list(matched.keys())].rename(columns=matched)

    # Inject static / derived columns
    for col, val in sheet_cfg.add_columns.items():
        df[col] = source_filename if val is None else val

    # In-batch dedup
    if sheet_cfg.dedup_column and sheet_cfg.dedup_column in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset=[sheet_cfg.dedup_column])
        dropped = before - len(df)
        if dropped:
            logger.info("    dedup on '{}': removed {} duplicate(s)", sheet_cfg.dedup_column, dropped)

    return df


# ── CSV writer ────────────────────────────────────────────────────────────────

def write_csv(df: pd.DataFrame, dest: Path, write_mode: str) -> None:
    """
    Write *df* to *dest*.

    overwrite
        Truncates the file and writes a fresh copy with headers.
    append
        Appends rows without header.  If the file already exists, aligns the
        incoming DataFrame to the existing columns (extra columns are dropped,
        missing columns are filled with empty string) so the CSV stays
        well-formed even when source schemas differ (e.g. POS vs ONLINE).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    if write_mode == "overwrite" or not dest.exists():
        df.to_csv(dest, index=False, encoding="utf-8")
        logger.info("    → wrote {} rows to {} (overwrite)", len(df), dest.name)
    else:
        # Align to existing schema so the CSV stays rectangular
        existing_cols = pd.read_csv(dest, nrows=0).columns.tolist()
        df = df.reindex(columns=existing_cols, fill_value="")
        df.to_csv(dest, mode="a", header=False, index=False, encoding="utf-8")
        logger.info("    → appended {} rows to {} (append)", len(df), dest.name)


# ── Per-file processing ───────────────────────────────────────────────────────

def _match_sheet_config(
    sheet_name: str, group: FileGroup
) -> SheetConfig | None:
    """Return the first enabled SheetConfig that matches sheet_name (case-insensitive).
    A sheet config with sheet='*' acts as a catch-all."""
    for sc in group.sheets:
        if not sc.enabled:
            continue
        if sc.sheet == "*" or sc.sheet.lower() == sheet_name.lower():
            return sc
    return None


def process_file(
    fpath: Path,
    group: FileGroup,
    downstream_dir: Path,
    settings: PipelineSettings,
) -> None:
    logger.info("[{}] {}", group.name, fpath.name)

    try:
        sheets_data = read_workbook(fpath)
    except Exception as exc:
        logger.error("  Failed to open {}: {}", fpath.name, exc)
        return

    if not sheets_data:
        logger.warning("  No readable sheets in {} — skipping", fpath.name)
        return

    for sheet_name, df_raw in sheets_data.items():
        sheet_cfg = _match_sheet_config(sheet_name, group)
        if sheet_cfg is None:
            logger.debug("  Sheet '{}' — no matching config, skipped", sheet_name)
            continue

        if df_raw.empty:
            logger.warning("  Sheet '{}' is empty — skipped", sheet_name)
            continue

        logger.info("  Sheet '{}': {} raw rows", sheet_name, len(df_raw))

        # Clean → map → write
        df = clean_dataframe(df_raw.copy(), settings)
        df = apply_sheet_config(df, sheet_cfg, fpath.name)

        if df.empty:
            logger.warning("  Sheet '{}' empty after cleaning — skipped", sheet_name)
            continue

        target = downstream_dir / sheet_cfg.target_csv
        write_csv(df, target, sheet_cfg.write_mode)


# ── Pipeline orchestrator ─────────────────────────────────────────────────────

def run_pipeline(root: Path, config: IngestionConfig) -> None:
    """Process all enabled file groups in declaration order."""
    downstream_dir = root / config.settings.downstream_dir
    downstream_dir.mkdir(parents=True, exist_ok=True)

    for group in config.file_groups:
        if not group.enabled:
            logger.info("Skipping disabled group: {}", group.name)
            continue

        src_dir = root / group.dir
        if not src_dir.exists():
            logger.warning("Source dir not found: {} — skipping group '{}'", src_dir, group.name)
            continue

        files = sorted(src_dir.glob(group.file_pattern))
        if not files:
            logger.warning(
                "No files matching '{}' in {} — skipping group '{}'",
                group.file_pattern, src_dir, group.name,
            )
            continue

        for fpath in files:
            process_file(fpath, group, downstream_dir, config.settings)

    logger.info("Pipeline complete. CSVs written to: {}", downstream_dir)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="CPG Analytics ingestion pipeline — reads Excel, writes downstream CSVs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m src.ingestion.pipeline\n"
            "  python -m src.ingestion.pipeline --config config/ingestion.json\n"
            "  python -m src.ingestion.pipeline --root /data/project\n"
        ),
    )
    parser.add_argument("--root", default=".", help="Repo root (default: cwd)")
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to ingestion.json (default: <root>/config/ingestion.json or INGESTION_CONFIG env var)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    settings = get_settings()
    cfg_path = Path(args.config) if args.config else root / settings.ingestion_config

    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    )

    config = load_config(cfg_path)
    logger.info(
        "Config loaded from {} — {} file group(s)",
        cfg_path.name, len(config.file_groups),
    )

    run_pipeline(root, config)


if __name__ == "__main__":
    _cli()
