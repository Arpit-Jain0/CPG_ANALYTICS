"""
src/ingestion/config_loader.py

Loads config/ingestion.json into typed dataclasses.
No Pydantic overhead — plain stdlib dataclasses + json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SheetConfig:
    """Routing rule for one worksheet (or '*' for all sheets in the file)."""

    sheet: str  # exact sheet name or "*" (match all)
    target_csv: str  # output filename in downstream_dir
    write_mode: str = "append"  # "overwrite" | "append"
    enabled: bool = True
    column_map: dict[str, str] = field(default_factory=dict)
    # Static columns to inject; value=None means use the source filename at runtime
    add_columns: dict[str, Any] = field(default_factory=dict)
    # Optional: deduplicate rows on this column before writing
    dedup_column: str | None = None
    # DQ pre-check: logical primary key column (post-clean lowercased name)
    pk_column: str | None = None
    # DQ pre-check: column → rule; rules: "numeric" | "positive_numeric" | "datetime"
    datatype_rules: dict[str, str] = field(default_factory=dict)
    # Postgres target tables (schema.table notation); None = skip DB write for this sheet
    raw_table: str | None = None  # e.g. "raw.pos_transactions"
    curated_table: str | None = None  # e.g. "curated.sales_transactions"


@dataclass
class FileGroup:
    """A logical group of files that share the same routing rules."""

    name: str
    dir: str  # relative path from repo root
    file_pattern: str  # glob — e.g. "*.xlsx", "*pos*.xlsx"
    sheets: list[SheetConfig]
    description: str = ""
    enabled: bool = True


@dataclass
class PipelineSettings:
    header_scan_rows: int = 15
    null_values: list[str] = field(
        default_factory=lambda: ["", "NA", "N/A", "NULL", "None", "nan", "NaN"]
    )
    date_formats: list[str] = field(default_factory=list)
    downstream_dir: str = "data/output/downstream"
    quality_reports_dir: str = "data/output/quality_reports"
    archive_dir: str = "data/archive"


@dataclass
class IngestionConfig:
    settings: PipelineSettings
    file_groups: list[FileGroup]


def load_config(path: Path | str) -> IngestionConfig:
    """Parse ingestion.json and return a typed IngestionConfig."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Ingestion config not found: {path}")

    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    # Settings — only known keys forwarded; unknown keys silently ignored
    _s = raw.get("settings", {})
    settings = PipelineSettings(
        header_scan_rows=_s.get("header_scan_rows", 15),
        null_values=_s.get(
            "null_values", PipelineSettings.__dataclass_fields__["null_values"].default_factory()
        ),
        date_formats=_s.get("date_formats", []),
        downstream_dir=_s.get("downstream_dir", "data/output/downstream"),
        quality_reports_dir=_s.get("quality_reports_dir", "data/output/quality_reports"),
        archive_dir=_s.get("archive_dir", "data/archive"),
    )

    groups: list[FileGroup] = []
    for g in raw.get("file_groups", []):
        sheets: list[SheetConfig] = []
        for s in g.get("sheets", []):
            sheets.append(
                SheetConfig(
                    sheet=s["sheet"],
                    target_csv=s["target_csv"],
                    write_mode=s.get("write_mode", "append"),
                    enabled=s.get("enabled", True),
                    column_map=s.get("column_map", {}),
                    add_columns=s.get("add_columns", {}),
                    dedup_column=s.get("dedup_column"),
                    pk_column=s.get("pk_column"),
                    datatype_rules=s.get("datatype_rules", {}),
                    raw_table=s.get("raw_table"),
                    curated_table=s.get("curated_table"),
                )
            )
        groups.append(
            FileGroup(
                name=g["name"],
                dir=g["dir"],
                file_pattern=g["file_pattern"],
                sheets=sheets,
                description=g.get("description", ""),
                enabled=g.get("enabled", True),
            )
        )

    return IngestionConfig(settings=settings, file_groups=groups)
