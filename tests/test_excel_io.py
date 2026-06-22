"""
tests/test_excel_io.py

Unit tests for src/common/excel_io.py.  No database or network I/O.

Scenarios
---------
- Leading title row is detected and skipped; real header is used.
- Ghost / empty sheets are silently ignored.
- When target_sheets is supplied, only the named sheet is returned.
- Requesting a non-existent target sheet raises KeyError.
- infer_source_system maps filenames/sheet names to source labels.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.excel_io import infer_source_system, read_workbook

# ── Title-row detection ────────────────────────────────────────────────────────


def test_title_row_skipped(wb_factory):
    """
    A workbook whose first row is a single-cell title (fills only 1 column)
    and whose second row is the real header (fills all columns) should be
    read with the second row as columns, not the first.
    """
    sheets = {
        "Sales": [
            ["Monthly Sales Report", None, None, None],  # title row — sparse
            ["transaction_id", "store_id", "amount", "date"],  # real header
            ["T001", "S01", 100.0, "2024-01-01"],
            ["T002", "S02", 200.0, "2024-01-02"],
        ]
    }
    path = wb_factory("with_title.xlsx", sheets)
    result = read_workbook(path)

    assert "Sales" in result
    df = result["Sales"]
    assert list(df.columns) == ["transaction_id", "store_id", "amount", "date"]
    assert len(df) == 2


def test_title_row_data_intact(wb_factory):
    """Data rows below the title row are not lost."""
    sheets = {
        "Data": [
            ["Q1 Report"],
            ["sku", "qty", "revenue"],
            ["SKU001", 10, 500.0],
        ]
    }
    path = wb_factory("title_data.xlsx", sheets)
    df = read_workbook(path)["Data"]
    assert df["sku"].iloc[0] == "SKU001"
    assert float(df["revenue"].iloc[0]) == 500.0


# ── Ghost-sheet detection ──────────────────────────────────────────────────────


def test_ghost_sheet_ignored(wb_factory):
    """A sheet with no cell content is silently skipped."""
    sheets = {
        "RealData": [
            ["id", "value"],
            [1, 42],
        ],
        "EmptySheet": [],  # no rows → ghost
    }
    path = wb_factory("with_ghost.xlsx", sheets)
    result = read_workbook(path)

    assert "RealData" in result
    assert "EmptySheet" not in result


def test_all_ghost_returns_empty(tmp_path):
    """A workbook where all sheets are empty returns an empty dict."""
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.title = "Ghost"
    # Leave the sheet completely blank
    path = tmp_path / "all_ghost.xlsx"
    wb.save(str(path))

    result = read_workbook(path)
    assert result == {}


# ── Target-sheet selection ─────────────────────────────────────────────────────


def test_target_sheet_by_name(wb_factory):
    """Only the explicitly requested sheet is returned."""
    sheets = {
        "Sales": [["id", "amount"], [1, 99]],
        "Notes": [["note"], ["ignore me"]],
        "Admin": [["key", "val"], ["x", "y"]],
    }
    path = wb_factory("multi_sheet.xlsx", sheets)
    result = read_workbook(path, target_sheets=["Sales"])

    assert list(result.keys()) == ["Sales"]
    assert "Notes" not in result
    assert "Admin" not in result


def test_unknown_target_sheet_raises(wb_factory):
    """Requesting a sheet that doesn't exist raises KeyError."""
    sheets = {"Data": [["id"], [1]]}
    path = wb_factory("single.xlsx", sheets)
    with pytest.raises(KeyError, match="NonExistent"):
        read_workbook(path, target_sheets=["NonExistent"])


# ── Source-system inference ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename,sheet,expected",
    [
        ("pos_history_2024.xlsx", "Sales", "POS"),
        ("online_orders.xlsx", "Orders", "ONLINE"),
        ("promo_data.xlsx", "promos", "PROMO"),
        ("campaign_q1.xlsx", "campaign_spend", "MARKETING"),
        ("competitor.xlsx", "prices", "COMPETITOR"),
        ("unknown_file.xlsx", "Sheet1", "UNKNOWN"),
    ],
)
def test_infer_source_system(filename, sheet, expected):
    assert infer_source_system(Path(filename), sheet) == expected
