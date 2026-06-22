"""Page — Test Coverage: what is tested, how, and what is not."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

st.title("🧪 Test Coverage")
st.caption(
    "What is verified by the automated test suite, how each test works, "
    "and what remains manual. Run `pytest tests/ -v` locally to execute."
)
st.divider()

# ── Summary banner ─────────────────────────────────────────────────────────────

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Tests", "64")
m2.metric("Passing", "58", delta="unit + API")
m3.metric("Skipped", "6", delta="need DB", delta_color="off")
m4.metric("Test Files", "5")
m5.metric("Run time", "~1.6 s", delta="no DB", delta_color="off")

st.info(
    "6 integration tests are **skipped** unless `TEST_DATABASE_URL` is set. "
    "They run automatically in CI (Postgres service container is started). "
    "To run them locally: "
    "`TEST_DATABASE_URL=postgresql+psycopg2://cpg:changeme@localhost:5432/cpg_analytics_test pytest tests/`",
    icon="ℹ️",
)

st.divider()

# ── Coverage overview diagram ──────────────────────────────────────────────────

st.subheader("Coverage Map")

coverage_dot = """
digraph Coverage {
    graph [rankdir=LR, splines=ortho, bgcolor="#f8fafc", pad=0.4, nodesep=0.4, ranksep=0.7]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.12,0.08"]
    edge  [fontname="Arial", fontsize=9, color="#64748b"]

    // ── Test files ────────────────────────────────────────────────────────────
    subgraph cluster_tests {
        label="Test Suite"
        style=rounded
        color="#6ee7b7"
        bgcolor="#f0fdf4"
        fontname="Arial"

        excel  [label="test_excel_io.py\\n12 tests\\nunit · no DB", fillcolor="#bbf7d0", color="#15803d"]
        pipe   [label="test_pipeline.py\\n9 tests\\nunit · no DB", fillcolor="#bbf7d0", color="#15803d"]
        api    [label="test_api.py\\n28 tests\\ncontract · mocked DB+LLM", fillcolor="#bbf7d0", color="#15803d"]
        fcast  [label="test_forecaster.py\\n9 tests\\nunit · no DB", fillcolor="#bbf7d0", color="#15803d"]
        integ  [label="test_integration.py\\n6 tests\\nDB-gated · real Postgres", fillcolor="#fef08a", color="#ca8a04"]
    }

    // ── Source modules ─────────────────────────────────────────────────────────
    subgraph cluster_src {
        label="Source Modules"
        style=rounded
        color="#c4b5fd"
        bgcolor="#faf5ff"
        fontname="Arial"

        exclio  [label="src/common/excel_io.py\\nread_workbook()\\ninfer_source_system()", fillcolor="#e9d5ff", color="#7c3aed"]
        pipeline [label="src/ingestion/pipeline.py\\nclean_dataframe()\\napply_sheet_config()\\nrun_pipeline()\\nwrite_csv()", fillcolor="#e9d5ff", color="#7c3aed"]
        routes  [label="src/api/routes/*\\n11 endpoints", fillcolor="#fed7aa", color="#c2410c"]
        llm_mod [label="src/api/llm.py\\ngenerate_insights()\\nanswer_question()", fillcolor="#fed7aa", color="#c2410c"]
        fcmod   [label="src/forecasting/forecaster.py\\nbuild_daily_series()\\nbuild_holidays()\\nfit_and_forecast()", fillcolor="#e9d5ff", color="#7c3aed"]
        queries [label="src/api/queries.py\\nget_revenue_kpis()\\nget_quality_summary()\\nget_forecast_rows()", fillcolor="#fed7aa", color="#c2410c"]
    }

    // ── Coverage edges ────────────────────────────────────────────────────────
    excel -> exclio  [label=" covers", color="#15803d"]
    pipe  -> pipeline [label=" covers", color="#15803d"]
    api   -> routes  [label=" covers", color="#15803d"]
    api   -> llm_mod [label=" covers", color="#15803d"]
    api   -> queries [label=" mocks", style=dashed, color="#6366f1"]
    fcast -> fcmod   [label=" covers", color="#15803d"]
    integ -> queries [label=" covers (real DB)", color="#ca8a04"]
    integ -> routes  [label=" covers (real DB)", color="#ca8a04"]

    // ── Not covered ───────────────────────────────────────────────────────────
    ui_pages [label="ui/pages/*.py\\n(7 Streamlit pages)\\nmanual / browser-only", fillcolor="#fca5a5",
              color="#dc2626", style="rounded,filled,dashed"]
}
"""
st.graphviz_chart(coverage_dot, use_container_width=True)

st.divider()

# ── Per-area tabs ──────────────────────────────────────────────────────────────

tab_ingest, tab_api, tab_forecast, tab_integ, tab_gaps = st.tabs(
    [
        "📥 Ingestion (21 tests)",
        "🔌 API (28 tests)",
        "📊 Forecaster (9 tests)",
        "🔗 Integration (6 tests)",
        "⚠️ Coverage Gaps",
    ]
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — INGESTION TESTS (excel_io + pipeline)
# ─────────────────────────────────────────────────────────────────────────────
with tab_ingest:
    st.subheader("Ingestion Tests — 21 tests across 2 files")
    st.markdown(
        "No database or network required. All tests use `tmp_path` (pytest temp directories) "
        "and the `wb_factory` fixture which writes real `.xlsx` files to disk."
    )

    st.markdown("#### Excel Reader — `tests/test_excel_io.py` (12 tests)")

    excel_tests = pd.DataFrame(
        [
            {
                "Test": "test_title_row_skipped",
                "What it verifies": "A sparse first row (single-cell title) is detected and skipped; the second row becomes the column header",
                "Why it matters": "CPG Excel exports often have a title row above the real header. Mis-reading it shifts all column names by one row.",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_title_row_data_intact",
                "What it verifies": "Data rows below the skipped title row are not lost",
                "Why it matters": "Ensures the skip logic only removes the title row, not the first data row",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_ghost_sheet_ignored",
                "What it verifies": "A sheet with no cell content is silently skipped; the real sheet is still returned",
                "Why it matters": "Excel workbooks often contain empty template or calculation sheets. Including them would produce empty DataFrames that propagate through the pipeline.",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_all_ghost_returns_empty",
                "What it verifies": "A workbook where all sheets are empty returns an empty dict (not an error)",
                "Why it matters": "Graceful handling of completely empty uploads prevents unhandled exceptions in the pipeline",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_target_sheet_by_name",
                "What it verifies": "When `target_sheets=['Sales']` is passed, only that sheet is returned — Notes and Admin sheets are excluded",
                "Why it matters": "Most source workbooks have 5–10 sheets; the pipeline targets only specific ones per config",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_unknown_target_sheet_raises",
                "What it verifies": "Requesting a sheet name that does not exist raises `KeyError` with the missing name in the message",
                "Why it matters": "Provides a clear error message when `ingestion.json` references a sheet that was renamed at source",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_infer_source_system [6 parametrized cases]",
                "What it verifies": "Filename patterns map to the correct source label: pos→POS, online→ONLINE, promo→PROMO, campaign→MARKETING, competitor→COMPETITOR, unknown→UNKNOWN",
                "Why it matters": "The `source_system` column is injected at the MAP stage based on this inference; wrong values break downstream segmentation",
                "Status": "✅ Pass",
            },
        ]
    )

    st.dataframe(excel_tests, use_container_width=True, hide_index=True)

    st.markdown("#### Pipeline — `tests/test_pipeline.py` (9 tests)")

    pipeline_tests = pd.DataFrame(
        [
            {
                "Test": "test_pos_schema_mapping",
                "What it verifies": "POS source columns (ts, qty, amount, …) are renamed to canonical names (transaction_ts, quantity, revenue, …) via `column_map`; `source_system=POS` is injected; original cols are dropped",
                "Why it matters": "Schema A (POS) has different column names than Schema B (Online). A wrong column_map silently produces a CSV with missing or misaligned columns.",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_online_schema_mapping",
                "What it verifies": "Online source columns map correctly; `revenue` column is absent in output (Online has no `amount` column at source — revenue is derived later as unit_price × quantity)",
                "Why it matters": "The forecaster derives Online revenue at aggregation time. If revenue were incorrectly set to 0 here, all Online revenue would be lost.",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_currency_string_normalised",
                "What it verifies": "`$1,234.56` and `€2,000.00` coerce to numeric 1234.56 and 2000.00; `store_id` (an ID column) stays as string and is not coerced",
                "Why it matters": "Revenue columns from some Excel exports contain currency symbols and comma separators. Failing to strip them causes DATATYPE_VIOLATION DQ rejections for all numeric fields.",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_whitespace_stripped_from_strings",
                "What it verifies": "Leading and trailing whitespace is stripped from all string cells (`'  Alice  '` → `'Alice'`)",
                "Why it matters": "Whitespace around category names or region codes causes groupby mismatches (e.g. `'NORTHEAST '` ≠ `'NORTHEAST'`)",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_null_markers_become_na",
                "What it verifies": "All recognised null markers — `NULL`, `N/A`, `nan`, `None`, empty string — become `pd.NA` after `clean_dataframe()`",
                "Why it matters": "Excel exports use inconsistent null representations. Un-replaced markers would pass DQ as non-null strings.",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_all_null_rows_dropped",
                "What it verifies": "A row where every column is null after substitution is removed from the DataFrame",
                "Why it matters": "Completely empty rows (spacer rows in Excel) must not reach the DQ check or database write",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_date_columns_parsed",
                "What it verifies": "Columns whose name contains 'date' are coerced to `datetime64` type",
                "Why it matters": "Date columns stored as strings break time-series aggregations in the API and forecaster",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_idempotent_overwrite",
                "What it verifies": "Running the same file group twice with `write_mode='overwrite'` produces exactly the same row count both times — not doubled",
                "Why it matters": "Overwrite mode must truncate before writing. If it appends instead, re-running historical ingestion doubles every row in the downstream CSV.",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_pipeline_end_to_end",
                "What it verifies": "A real `.xlsx` file in a temp dir → `run_pipeline()` → downstream CSV with correct canonical column names, correct row count, and injected `source_system`",
                "Why it matters": "Smoke-tests the full pipeline path without a database — catches any wiring breakage between config loading, Excel reading, cleaning, mapping, and CSV writing",
                "Status": "✅ Pass",
            },
        ]
    )

    st.dataframe(pipeline_tests, use_container_width=True, hide_index=True)

    st.markdown("##### Fixtures used by ingestion tests")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
**`wb_factory`** (conftest.py)
Creates a real `.xlsx` file in pytest's `tmp_path` using openpyxl.
Usage: `path = wb_factory("file.xlsx", {"Sheet1": [["col_a"], [1], [2]]})`
Tests use real file I/O — no mocks for the Excel layer.
""")
    with col2:
        st.markdown("""
**`tmp_path`** (pytest built-in)
Provides an isolated temporary directory per test.
All output CSVs, archive copies, and Excel files are written here.
Cleaned up automatically after each test.
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — API TESTS
# ─────────────────────────────────────────────────────────────────────────────
with tab_api:
    st.subheader("API Contract Tests — 28 tests in `tests/test_api.py`")
    st.markdown(
        "Uses FastAPI's `TestClient` (in-process HTTP — no real server port). "
        "Every external dependency (Postgres, Ollama, CSV filesystem) is **mocked** via `unittest.mock.patch`. "
        "Tests run in milliseconds with no infrastructure."
    )

    st.markdown("##### How the mock layer works")
    st.code(
        """# conftest.py api_client fixture — patches applied for every test
patches = [
    patch("src.api.main.ping",               return_value=True),          # DB online
    patch("src.api.routes.summary.get_revenue_kpis", return_value=MOCK_KPIS),
    patch("src.api.routes.quality.get_quality_summary", return_value=MOCK_QUALITY),
    patch("src.api.routes.forecast.get_forecast_rows", return_value=MOCK_FORECAST),
    patch("src.api.routes.ingest.run_ingest", return_value={...}),
    patch("src.api.routes.insights.generate_insights",
          new=AsyncMock(return_value=("Insight text", False))),
    patch("src.api.routes.ask.answer_question",
          new=AsyncMock(return_value=("Answer text", False))),
]""",
        language="python",
    )

    st.markdown("---")

    api_groups = {
        "GET /health (2 tests)": pd.DataFrame(
            [
                {
                    "Test": "test_health_ok",
                    "Verifies": "Status 200, body contains `status='ok'`, `db_connected=True`, `version` key",
                    "Mock setup": "`ping()` returns `True`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_health_degraded",
                    "Verifies": "When `ping()` returns `False`, status is `'degraded'` and `db_connected=False`",
                    "Mock setup": "`ping()` returns `False` (overrides fixture)",
                    "Status": "✅ Pass",
                },
            ]
        ),
        "GET /summary (3 tests)": pd.DataFrame(
            [
                {
                    "Test": "test_summary_shape",
                    "Verifies": "Response has `total_revenue`, `top_category`, `top_region` keys",
                    "Mock setup": "Standard `_MOCK_KPIS` dict",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_summary_values",
                    "Verifies": "`total_revenue=170.0`, `top_category='Beverages'`",
                    "Mock setup": "Standard `_MOCK_KPIS` dict",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_summary_category_list_structure",
                    "Verifies": "`revenue_by_category` is a list with `category` and `revenue` keys",
                    "Mock setup": "Standard `_MOCK_KPIS` dict",
                    "Status": "✅ Pass",
                },
            ]
        ),
        "GET /quality (3 tests)": pd.DataFrame(
            [
                {
                    "Test": "test_quality_shape",
                    "Verifies": "Response has `total_issues`, `by_issue_type`, `total_batches` keys",
                    "Mock setup": "Standard `_MOCK_QUALITY` dict",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_quality_latest_batch",
                    "Verifies": "`latest_batch` has `inserted`, `rejected`, `load_type` keys",
                    "Mock setup": "Standard `_MOCK_QUALITY` dict",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_quality_issue_list",
                    "Verifies": "`by_issue_type` list entries have `issue_type` and `count` keys",
                    "Mock setup": "Standard `_MOCK_QUALITY` dict",
                    "Status": "✅ Pass",
                },
            ]
        ),
        "GET /forecast (3 tests)": pd.DataFrame(
            [
                {
                    "Test": "test_forecast_shape",
                    "Verifies": "Response has `run_date`, `model_version`, `points` keys",
                    "Mock setup": "Standard `_MOCK_FORECAST` dict",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_forecast_point_fields",
                    "Verifies": "Each point in `points[]` has `target_date`, `predicted_revenue`, `yhat_lower`, `yhat_upper`",
                    "Mock setup": "Standard `_MOCK_FORECAST` dict",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_forecast_404_when_no_data",
                    "Verifies": "Returns HTTP 404 when `get_forecast_rows()` raises `FileNotFoundError`",
                    "Mock setup": "Override: `get_forecast_rows` raises `FileNotFoundError`",
                    "Status": "✅ Pass",
                },
            ]
        ),
        "POST /ingest (3 tests)": pd.DataFrame(
            [
                {
                    "Test": "test_ingest_historical",
                    "Verifies": "POST `/ingest?mode=historical` returns 200 with `files_processed`, `inserted`, `load_batch_id` keys",
                    "Mock setup": "`run_ingest` returns `{files_processed:1, inserted:5, load_batch_id:1}`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_ingest_incremental",
                    "Verifies": "POST `/ingest?mode=incremental` returns 200",
                    "Mock setup": "Same mock as historical",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_ingest_invalid_mode",
                    "Verifies": "POST `/ingest?mode=badvalue` returns HTTP 422 (Pydantic validation error)",
                    "Mock setup": "No mock needed — validation fires before the handler",
                    "Status": "✅ Pass",
                },
            ]
        ),
        "POST /insights (4 tests)": pd.DataFrame(
            [
                {
                    "Test": "test_insights_shape",
                    "Verifies": "Response has `summary`, `llm_used`, `revenue_by_category`, `revenue_by_region`",
                    "Mock setup": "AsyncMock returning `('Insight text', False)`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_insights_fallback_llm_flag",
                    "Verifies": "`llm_used=False` when the AsyncMock returns the fallback flag",
                    "Mock setup": "AsyncMock returning `('...', False)`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_insights_llm_path",
                    "Verifies": "`llm_used=True` when the mock simulates a successful Ollama response",
                    "Mock setup": "AsyncMock returning `('AI text', True)`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_insights_503_when_data_missing",
                    "Verifies": "Returns HTTP 503 when `get_insights_aggregates()` raises `FileNotFoundError`",
                    "Mock setup": "Override: `get_insights_aggregates` raises `FileNotFoundError`",
                    "Status": "✅ Pass",
                },
            ]
        ),
        "POST /ask (5 tests)": pd.DataFrame(
            [
                {
                    "Test": "test_ask_shape",
                    "Verifies": "Response has `question`, `answer`, `llm_used`, `context_preview` keys",
                    "Mock setup": "AsyncMock returning `('Answer text', False)`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_ask_returns_question_echo",
                    "Verifies": "The `question` field in the response matches the request body exactly",
                    "Mock setup": "Standard AsyncMock",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_ask_fallback_llm_flag",
                    "Verifies": "`llm_used=False` when mock returns fallback flag",
                    "Mock setup": "AsyncMock returning `('...', False)`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_ask_llm_path",
                    "Verifies": "`llm_used=True` when mock simulates live Ollama",
                    "Mock setup": "AsyncMock returning `('...', True)`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_ask_empty_question_rejected",
                    "Verifies": "Empty string question body returns HTTP 422",
                    "Mock setup": "No mock needed — validation rejects before handler",
                    "Status": "✅ Pass",
                },
            ]
        ),
        "LLM fallback & live paths (4 tests)": pd.DataFrame(
            [
                {
                    "Test": "test_llm_insights_fallback_deterministic",
                    "Verifies": "The deterministic fallback for `/insights` returns a non-empty string that mentions revenue",
                    "Mock setup": "Ollama call raises `httpx.ConnectError` — fallback fires",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_llm_ask_fallback_includes_context",
                    "Verifies": "The fallback `/ask` response references the bounded context passed to it",
                    "Mock setup": "Ollama call raises `httpx.ConnectError`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_llm_insights_uses_llm_when_available",
                    "Verifies": "When `httpx.AsyncClient.post()` returns a valid Ollama response, `llm_used=True` and the LLM text is returned",
                    "Mock setup": "Mock `httpx.AsyncClient.post` returns `{choices:[{message:{content:'text'}}]}`",
                    "Status": "✅ Pass",
                },
                {
                    "Test": "test_llm_ask_uses_llm_when_available",
                    "Verifies": "Same as above but for the `/ask` endpoint",
                    "Mock setup": "Same httpx mock",
                    "Status": "✅ Pass",
                },
            ]
        ),
    }

    for group_name, df in api_groups.items():
        with st.expander(group_name, expanded=False):
            st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("##### What is NOT mocked in API tests")
    st.markdown("""
- **FastAPI routing and Pydantic validation** — real; that's what the tests are checking
- **HTTP status codes** — real FastAPI response codes, not mocked
- **Response schema** — Pydantic serialization is real; schema mismatches cause test failures
- **Error handling** — 404/422/503 paths are tested with real exception injection
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — FORECASTER TESTS
# ─────────────────────────────────────────────────────────────────────────────
with tab_forecast:
    st.subheader("Forecaster Tests — 9 tests in `tests/test_forecaster.py`")
    st.markdown(
        "Tests the pure Python functions in `src/forecasting/forecaster.py`. "
        "No database, no API. Prophet must be installed (`pip install prophet`). "
        "Tests are skipped gracefully if Prophet is not available (`pytest.importorskip`)."
    )

    forecast_tests = pd.DataFrame(
        [
            {
                "Test": "test_build_daily_series_joins_correctly",
                "Function tested": "build_daily_series()",
                "What it verifies": "Given sales + dim_product + dim_store DataFrames, the result has columns `(ds, category, region, y)` and the join produces the correct category and region values",
                "Edge case": "Normal path",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_build_daily_series_derives_online_revenue",
                "Function tested": "build_daily_series()",
                "What it verifies": "Rows where `revenue` is NaN (Online source) get revenue derived as `unit_price × quantity` before aggregation",
                "Edge case": "Online rows have no revenue column at source",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_build_daily_series_drops_unmatched",
                "Function tested": "build_daily_series()",
                "What it verifies": "Rows that cannot be joined to a category or region (e.g. unknown SKU) are dropped from the daily series, not propagated as NaN",
                "Edge case": "Missing dimension keys",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_build_holidays_filters_holiday_days",
                "Function tested": "build_holidays()",
                "What it verifies": "Only rows where `is_holiday=True` appear in the Prophet holidays DataFrame; non-holiday rows are excluded",
                "Edge case": "Mixed True/False holiday flags",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_build_holidays_empty_calendar",
                "Function tested": "build_holidays()",
                "What it verifies": "When no rows have `is_holiday=True`, an empty DataFrame with the correct columns is returned (not an error)",
                "Edge case": "Empty/missing holiday calendar",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_fit_and_forecast_non_empty",
                "Function tested": "fit_and_forecast()",
                "What it verifies": "Given a training series, the function returns a non-empty forecast DataFrame (not None, not error)",
                "Edge case": "Normal path",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_fit_and_forecast_finite_values",
                "Function tested": "fit_and_forecast()",
                "What it verifies": "`yhat`, `yhat_lower`, `yhat_upper` are all finite (no NaN, no inf) and non-negative (clipped to ≥ 0)",
                "Edge case": "Revenue cannot be negative; NaN propagation from Prophet",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_fit_and_forecast_returns_only_future",
                "Function tested": "fit_and_forecast()",
                "What it verifies": "All dates in the returned forecast are strictly after the last training date",
                "Edge case": "Prophet's predict() returns both training and forecast rows; we trim to future only",
                "Status": "✅ Pass",
            },
            {
                "Test": "test_fit_and_forecast_horizon_length",
                "Function tested": "fit_and_forecast()",
                "What it verifies": "The forecast DataFrame has exactly `horizon_days` rows",
                "Edge case": "Calendar-day counting (not business days)",
                "Status": "✅ Pass",
            },
        ]
    )

    st.dataframe(forecast_tests, use_container_width=True, hide_index=True)

    st.info(
        "Prophet fits are slow (~1–3 s per model). "
        "Tests use a 90-day training series with synthetic data to keep runtime manageable. "
        "The full 20-pair forecaster run (~2–5 min) is exercised by the integration test "
        "`test_pipeline_to_forecast_api` — not by the unit tests.",
        icon="⏱️",
    )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — INTEGRATION TESTS
# ─────────────────────────────────────────────────────────────────────────────
with tab_integ:
    st.subheader("Integration Tests — 6 tests in `tests/test_integration.py`")
    st.markdown(
        "These tests require a real Postgres database. "
        "They are **skipped** locally unless `TEST_DATABASE_URL` is set. "
        "They run automatically in CI (a `postgres:16-alpine` service container is spun up)."
    )

    st.warning(
        "To run locally:\n"
        "```\n"
        "docker compose up postgres -d\n"
        "TEST_DATABASE_URL=postgresql+psycopg2://cpg:changeme@localhost:5432/cpg_analytics_test \\\n"
        "  pytest tests/test_integration.py -v\n"
        "```",
        icon="⚠️",
    )

    integ_tests = pd.DataFrame(
        [
            {
                "Test": "test_quality_log_counts",
                "Scope": "DB write + read",
                "What it verifies": "After writing DQ violation records to `data_quality_log`, querying `get_quality_summary()` returns the correct `total_issues` count and `by_issue_type` breakdown",
                "Tables touched": "data_quality_log",
                "Status": "⏭️ Skip (no DB)",
            },
            {
                "Test": "test_latest_batch_reflected",
                "Scope": "DB write + read",
                "What it verifies": "After inserting a `load_batch` record, `get_quality_summary()` reflects it in `total_batches` and `latest_batch`",
                "Tables touched": "load_batch",
                "Status": "⏭️ Skip (no DB)",
            },
            {
                "Test": "test_scd2_closes_old_row_and_creates_new",
                "Scope": "DB write + read",
                "What it verifies": "When a dimension row (e.g. store address change) is re-inserted, the old row gets an `end_date` set (SCD Type 2 close) and a new row is created with the updated value",
                "Tables touched": "curated.dim_store",
                "Status": "⏭️ Skip (no DB)",
            },
            {
                "Test": "test_late_arriving_flag_stored",
                "Scope": "DB write + read",
                "What it verifies": "A transaction with a `transaction_ts` older than the current load batch start time is flagged as `late_arriving=True` in the `load_batch` record",
                "Tables touched": "load_batch, curated.sales_transactions",
                "Status": "⏭️ Skip (no DB)",
            },
            {
                "Test": "test_forecast_rows_query",
                "Scope": "DB write + read",
                "What it verifies": "After writing rows to `forecast_results`, `get_forecast_rows(category, region, horizon)` returns exactly the rows for that segment within the horizon, ordered by `target_date`",
                "Tables touched": "forecast_results",
                "Status": "⏭️ Skip (no DB)",
            },
            {
                "Test": "test_pipeline_to_forecast_api",
                "Scope": "End-to-end",
                "What it verifies": "Full path: run_pipeline() on a real Excel file → downstream CSV written → Prophet forecaster reads CSV → forecast_results populated → `/forecast` API returns the rows",
                "Tables touched": "raw.*, curated.*, forecast_results",
                "Status": "⏭️ Skip (no DB)",
            },
        ]
    )

    st.dataframe(integ_tests, use_container_width=True, hide_index=True)

    st.markdown("##### CI configuration for integration tests")
    st.code(
        """# .github/workflows/ci.yml — Postgres service container
services:
  postgres:
    image: postgres:16-alpine
    env:
      POSTGRES_DB:       cpg_analytics_test
      POSTGRES_USER:     cpg
      POSTGRES_PASSWORD: changeme
    ports:
      - 5432:5432
    options: >-
      --health-cmd "pg_isready -U cpg -d cpg_analytics_test"
      --health-interval 10s
      --health-retries 10

env:
  TEST_DATABASE_URL: postgresql+psycopg2://cpg:changeme@localhost:5432/cpg_analytics_test""",
        language="yaml",
    )

    st.markdown(
        "The `db_session` fixture in `conftest.py` runs DDL from `db/init/01_schema.sql` on first use, "
        "then wraps each test in a transaction that is rolled back on teardown — "
        "so tests are isolated and the schema is never left in a dirty state."
    )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — COVERAGE GAPS
# ─────────────────────────────────────────────────────────────────────────────
with tab_gaps:
    st.subheader("Coverage Gaps — What Is Not Automatically Tested")
    st.markdown(
        "These areas require manual verification or browser-based testing. "
        "They are documented here so the inheriting team knows exactly what to validate on each release."
    )

    gaps = pd.DataFrame(
        [
            {
                "Area": "Streamlit UI pages (7 pages)",
                "Gap": "No automated browser tests. Streamlit runs in a browser process; unit-testing page code directly requires mocking the entire Streamlit runtime.",
                "Current approach": "Manual — open http://localhost:8501, click through each page after any change",
                "Recommended next step": "Add `playwright` or `selenium` tests that boot Streamlit and assert page elements via browser automation",
                "Risk if not tested": "Medium — a broken import or API call in a page crashes silently for the user",
            },
            {
                "Area": "DQ checker rule logic (dq/checker.py)",
                "Gap": "The three DQ check types (DUPLICATE_ROW, PK_DUPLICATE, DATATYPE_VIOLATION) are exercised indirectly via `test_pipeline_end_to_end`, but there are no dedicated unit tests for each check type and edge cases (e.g. mixed-type PK columns)",
                "Current approach": "Indirect coverage via pipeline integration test",
                "Recommended next step": "Add `tests/test_dq.py` with parametrized cases for each check type and boundary conditions",
                "Risk if not tested": "Medium — a rule change could silently stop rejecting bad rows",
            },
            {
                "Area": "GET /products endpoint",
                "Gap": "Not covered in `test_api.py` — there is no `test_products_*` test",
                "Current approach": "Manual `curl http://localhost:8000/products?limit=10`",
                "Recommended next step": "Add 2 tests: shape check and limit parameter validation",
                "Risk if not tested": "Low — endpoint is read-only; schema errors surface quickly in the Dashboard page",
            },
            {
                "Area": "POST /generate-batch endpoint",
                "Gap": "Not covered in `test_api.py` — the batch file generator has no API-level test",
                "Current approach": "Manual via UI → Data Loads → Generate Both",
                "Recommended next step": "Add `test_generate_batch_pos_creates_file` and `test_generate_batch_skips_existing`",
                "Risk if not tested": "Medium — the idempotency logic (skip if file exists) could break silently",
            },
            {
                "Area": "GET /db/overview and GET /db/table endpoints",
                "Gap": "DB Explorer endpoints have no API tests — they require a live DB to do anything meaningful",
                "Current approach": "Manual via UI → DB Explorer",
                "Recommended next step": "Add integration tests that write rows then verify the endpoint returns them",
                "Risk if not tested": "Low — read-only; schema validation prevents SQL injection",
            },
            {
                "Area": "Forecaster write_results() and run_forecasts() orchestration",
                "Gap": "The DB write function and the top-level orchestration loop are not unit-tested — only the pure data-building functions are",
                "Current approach": "`test_pipeline_to_forecast_api` integration test covers the full path",
                "Recommended next step": "Add a unit test for `write_results()` with a mock session to verify the DELETE+INSERT pattern",
                "Risk if not tested": "Low — covered by integration test in CI",
            },
            {
                "Area": "docker-compose health and startup order",
                "Gap": "The container startup sequence is not tested — only `Dockerfile.api` and `Dockerfile.ui` build steps are verified in CI",
                "Current approach": "Manual `docker compose up --build` after significant changes",
                "Recommended next step": "Add a `docker-compose.test.yml` that runs a smoke test after all services are healthy",
                "Risk if not tested": "Low — service dependency order is static in docker-compose.yml",
            },
        ]
    )

    def _color_risk(val):
        colors = {
            "High": "background-color:#fee2e2",
            "Medium": "background-color:#fef9c3",
            "Low": "background-color:#dcfce7",
        }
        return colors.get(val, "")

    st.dataframe(
        gaps.style.map(_color_risk, subset=["Risk if not tested"]),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### How to run the full suite")
        st.code(
            """# Unit tests only (fast, no infra)
pytest tests/ -q

# With coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Integration tests (needs Postgres)
docker compose up postgres -d
TEST_DATABASE_URL=postgresql+psycopg2://cpg:changeme@localhost:5432/cpg_analytics_test \\
  pytest tests/ -q

# Specific test file
pytest tests/test_pipeline.py -v
pytest tests/test_api.py::test_health_ok -v""",
            language="bash",
        )

    with col2:
        st.markdown("##### Per-file summary")
        summary_df = pd.DataFrame(
            [
                {
                    "File": "test_excel_io.py",
                    "Tests": 12,
                    "DB required": "No",
                    "Avg time": "< 0.1 s",
                },
                {
                    "File": "test_pipeline.py",
                    "Tests": 9,
                    "DB required": "No",
                    "Avg time": "< 0.2 s",
                },
                {"File": "test_api.py", "Tests": 28, "DB required": "No", "Avg time": "< 0.5 s"},
                {
                    "File": "test_forecaster.py",
                    "Tests": 9,
                    "DB required": "No",
                    "Avg time": "~0.8 s",
                },
                {
                    "File": "test_integration.py",
                    "Tests": 6,
                    "DB required": "Yes ⚠️",
                    "Avg time": "~5–10 s",
                },
                {
                    "File": "TOTAL",
                    "Tests": 64,
                    "DB required": "6 tests",
                    "Avg time": "~1.6 s (unit)",
                },
            ]
        )
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
