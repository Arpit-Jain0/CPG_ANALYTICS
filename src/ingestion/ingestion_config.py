"""
src/ingestion/ingestion_config.py

Typed, validated representation of config/ingestion.yaml.

The config file governs:
  • Which Excel files and sheets are loaded for historical and incremental modes
  • The DB loader function assigned to each dimension/secondary sheet
  • Per-file toggles: enabled, archive_after_load, export_processed, late_arriving_detection
  • Incremental glob pattern and SCD-2 sheet name list
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

# ── Type aliases ──────────────────────────────────────────────────────────────

SheetRole = Literal["dimension", "secondary", "sales", "scd2_updates"]
SourceSystem = Literal["POS", "ONLINE", "auto"]
LoaderName = Literal[
    "dim_region",
    "dim_store",
    "dim_product_seed",
    "seasonal_calendar",
    "promo_windows",
    "marketing_campaigns",
    "competitor_prices",
]


# ── Sheet-level config ────────────────────────────────────────────────────────

class SheetConfig(BaseModel):
    """One worksheet within a source workbook."""

    name: str
    role: SheetRole
    enabled: bool = True
    #: Applies to role=sales; "auto" lets detect_source_system() decide.
    source_system: SourceSystem = "auto"
    #: Applies to role=dimension or role=secondary; maps to a registered loader function.
    loader: LoaderName | None = None


# ── File-level config ─────────────────────────────────────────────────────────

class FileConfig(BaseModel):
    """One source Excel workbook."""

    name: str
    description: str = ""
    enabled: bool = True
    #: None → inherit from IngestionDefaults
    archive_after_load: bool | None = None
    export_processed: bool | None = None
    export_quality_report: bool | None = None
    #: None → role-appropriate default (False for historical, True for incremental)
    late_arriving_detection: bool | None = None
    sheets: list[SheetConfig]

    def resolve_archive(self, defaults: "IngestionDefaults") -> bool:
        return self.archive_after_load if self.archive_after_load is not None else defaults.archive_after_load

    def resolve_export_processed(self, defaults: "IngestionDefaults") -> bool:
        return self.export_processed if self.export_processed is not None else defaults.export_processed

    def resolve_export_quality_report(self, defaults: "IngestionDefaults") -> bool:
        return self.export_quality_report if self.export_quality_report is not None else defaults.export_quality_report

    def resolve_late_arriving(self, *, fallback: bool) -> bool:
        return self.late_arriving_detection if self.late_arriving_detection is not None else fallback


# ── Mode-level configs ────────────────────────────────────────────────────────

class HistoricalConfig(BaseModel):
    source_dir: str
    files: list[FileConfig]


class IncrementalConfig(BaseModel):
    source_dir: str
    glob_pattern: str = "*.xlsx"
    late_arriving_detection: bool = True
    archive_after_load: bool = True
    export_processed: bool = True
    export_quality_report: bool = True
    #: Sheet names (case-insensitive) that carry SCD-2 product attribute changes.
    scd2_sheet_names: list[str] = Field(default_factory=lambda: ["product_updates"])

    def is_scd2_sheet(self, sheet_name: str) -> bool:
        return sheet_name.strip().lower() in {n.lower() for n in self.scd2_sheet_names}


# ── Top-level defaults ────────────────────────────────────────────────────────

class IngestionDefaults(BaseModel):
    archive_after_load: bool = True
    export_processed: bool = True
    export_quality_report: bool = True
    chunk_size: int = 500
    header_scan_rows: int = 15


# ── Root config ───────────────────────────────────────────────────────────────

class IngestionConfig(BaseModel):
    defaults: IngestionDefaults = Field(default_factory=IngestionDefaults)
    historical: HistoricalConfig
    incremental: IncrementalConfig


# ── Loader ────────────────────────────────────────────────────────────────────

def load_ingestion_config(path: Path | str) -> IngestionConfig:
    """Parse and validate a YAML ingestion config file.

    Raises FileNotFoundError when *path* does not exist, or ValidationError
    when the YAML does not match the expected schema.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Ingestion config not found: {path}")
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return IngestionConfig.model_validate(raw)
