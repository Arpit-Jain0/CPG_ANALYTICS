"""Page — Architecture & Data Flow: visual diagrams of every platform layer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.title("🏗️ Architecture & Data Flow")
st.caption(
    "Visual overview of every layer in the CPG Analytics platform — "
    "from raw Excel ingestion through Prophet forecasting to the Streamlit UI."
)
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_combined, tab_ingest, tab_forecast, tab_api, tab_container = st.tabs(
    [
        "🗺️ Combined Overview",
        "📥 Ingestion Pipeline",
        "📊 Forecasting Engine",
        "🔌 API & UI Layer",
        "🐳 Containerisation",
    ]
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — COMBINED OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
with tab_combined:
    st.subheader("Full Platform Architecture")
    st.markdown(
        "Every component in one view. " "Click individual tabs above to zoom into each layer."
    )

    combined_dot = """
digraph CPG {
    graph [rankdir=TB, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.6, ranksep=0.7]
    node  [fontname="Arial", fontsize=11, style="rounded,filled", margin="0.15,0.10"]
    edge  [fontname="Arial", fontsize=9, color="#64748b"]

    // ── Input sources ────────────────────────────────────────────────────────
    subgraph cluster_sources {
        label="Data Sources"
        style=rounded
        color="#93c5fd"
        bgcolor="#eff6ff"
        fontname="Arial"
        fontsize=12

        hist  [label="Historical Excel\\n(data/input/historical/)", fillcolor="#bfdbfe", color="#2563eb"]
        incr  [label="Weekly Batches\\n(data/input/incremental/)", fillcolor="#bfdbfe", color="#2563eb"]
    }

    // ── Ingestion pipeline ───────────────────────────────────────────────────
    subgraph cluster_pipeline {
        label="Ingestion Pipeline  (src/ingestion/)"
        style=rounded
        color="#6ee7b7"
        bgcolor="#f0fdf4"
        fontname="Arial"
        fontsize=12

        read    [label="1 READ\\nexcel_io.read_workbook()", fillcolor="#bbf7d0", color="#15803d"]
        archive [label="2 ARCHIVE\\ncopy → data/archive/", fillcolor="#bbf7d0", color="#15803d"]
        raw_w   [label="3 RAW WRITE\\nall cols as TEXT", fillcolor="#bbf7d0", color="#15803d"]
        clean   [label="4 CLEAN\\nnull repair · coerce", fillcolor="#bbf7d0", color="#15803d"]
        dq      [label="5 DQ CHECK\\nDUP · PK · DTYPE", fillcolor="#bbf7d0", color="#15803d"]
        write   [label="6 WRITE\\nCSV + curated tables*", fillcolor="#bbf7d0", color="#15803d"]

        read -> archive -> raw_w -> clean -> dq -> write
    }

    // ── Storage ──────────────────────────────────────────────────────────────
    subgraph cluster_storage {
        label="Storage  (PostgreSQL 16 + CSVs)"
        style=rounded
        color="#fbbf24"
        bgcolor="#fffbeb"
        fontname="Arial"
        fontsize=12

        pg_raw  [label="raw.*\\n10 tables (TEXT)", fillcolor="#fef08a", color="#ca8a04"]
        pg_cur  [label="curated.*\\n2 tables (typed)", fillcolor="#fef08a", color="#ca8a04"]
        pg_err  [label="error.*\\ndq_rejected_rows (JSONB)", fillcolor="#fca5a5", color="#dc2626"]
        csvs    [label="downstream/*.csv\\n9 clean files", fillcolor="#fef08a", color="#ca8a04"]
    }

    // ── Forecasting ──────────────────────────────────────────────────────────
    subgraph cluster_forecast {
        label="Forecasting  (src/forecasting/)"
        style=rounded
        color="#c4b5fd"
        bgcolor="#faf5ff"
        fontname="Arial"
        fontsize=12

        prophet [label="Prophet\\n20 models (5 cat × 4 reg)\\n90-day horizon · 90% CI", fillcolor="#e9d5ff", color="#7c3aed"]
        fc_tbl  [label="forecast_results\\n(Postgres table)", fillcolor="#e9d5ff", color="#7c3aed"]
    }

    // ── API ──────────────────────────────────────────────────────────────────
    subgraph cluster_api {
        label="FastAPI  (src/api/)  — 11 endpoints"
        style=rounded
        color="#fb923c"
        bgcolor="#fff7ed"
        fontname="Arial"
        fontsize=12

        api [label="FastAPI\\n/health /summary /quality\\n/forecast /ingest /ask\\n/insights /products /dq-reports\\n/generate-batch /db/*", fillcolor="#fed7aa", color="#c2410c"]
    }

    // ── LLM ─────────────────────────────────────────────────────────────────
    ollama [label="Ollama LLM\\n(local · offline · optional)", fillcolor="#fce7f3", color="#be185d",
            style="rounded,filled,dashed"]

    // ── UI ───────────────────────────────────────────────────────────────────
    subgraph cluster_ui {
        label="Streamlit UI  (ui/)"
        style=rounded
        color="#67e8f9"
        bgcolor="#ecfeff"
        fontname="Arial"
        fontsize=12

        ui [label="7 Pages\\n🏠 Home  📊 Dashboard\\n📈 Forecast  🤖 AI Q&A\\n🛡 DQ Reports  🔄 Data Loads\\n🗄 DB Explorer", fillcolor="#a5f3fc", color="#0e7490"]
    }

    // ── Edges ────────────────────────────────────────────────────────────────
    hist -> read
    incr -> read

    raw_w  -> pg_raw  [label=" raw TEXT"]
    dq     -> pg_err  [label=" rejected", color="#dc2626"]
    write  -> pg_cur  [label=" curated"]
    write  -> csvs    [label=" CSV"]

    csvs   -> prophet
    prophet -> fc_tbl

    csvs   -> api     [label=" read"]
    fc_tbl -> api     [label=" read"]
    pg_cur -> api     [label=" read", style=dashed]

    ollama -> api     [label=" optional", style=dashed, color="#be185d"]
    api    -> ui      [label=" JSON / HTTP"]
}
"""
    st.graphviz_chart(combined_dot, use_container_width=True)

    st.markdown("---")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### Key design rules")
        st.markdown("""
- UI never touches the database directly
- API reads CSVs for analytics queries (not Postgres)
- Raw rows **never** sent to the LLM — aggregates only
- Every pipeline stage is independently testable
""")
    with c2:
        st.markdown("##### Data boundaries")
        st.markdown("""
- `raw.*` — immutable audit trail; never updated
- `curated.*` — typed, DQ-passed, ON CONFLICT DO NOTHING
- `error.*` — rejected rows as JSONB
- `downstream/` — clean CSVs; the API's read layer
""")
    with c3:
        st.markdown("##### Tech stack")
        st.markdown("""
- **Pipeline** — Python 3.11 · pandas · openpyxl
- **DB** — PostgreSQL 16 · SQLAlchemy 2.x
- **Forecast** — Facebook Prophet 1.x
- **API** — FastAPI · Pydantic v2
- **UI** — Streamlit 1.35+ · Altair 5.x
- **LLM** — Ollama (local, OpenAI-compatible)
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — INGESTION PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
with tab_ingest:
    st.subheader("Ingestion Pipeline — 7-Stage Detail")
    st.markdown(
        "Every Excel file passes through the same seven stages in order. "
        "Stages 3, 5, and 7 each write to a different destination simultaneously."
    )

    ingest_dot = """
digraph Ingest {
    graph [rankdir=LR, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.5, ranksep=0.8]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.15,0.10"]
    edge  [fontname="Arial", fontsize=9]

    // Input
    xlsx [label="Excel Workbook\\n(.xlsx)", shape=note, fillcolor="#bfdbfe", color="#2563eb"]

    // Stages
    s1 [label="1  READ\\nread_workbook()\\n· skip ghost sheets\\n· auto-detect header", fillcolor="#bbf7d0", color="#15803d"]
    s2 [label="2  ARCHIVE\\narchive_file()\\n· copy original to\\ndata/archive/{date}/", fillcolor="#bbf7d0", color="#15803d"]
    s3 [label="3  RAW WRITE\\nwrite_raw()\\n· ALL cols as TEXT\\n· no filtering", fillcolor="#bbf7d0", color="#15803d"]
    s4 [label="4  CLEAN\\nclean_dataframe()\\n· lowercase cols\\n· null markers → NaN\\n· date / numeric coerce", fillcolor="#bbf7d0", color="#15803d"]
    s5 [label="5  DQ CHECK\\nrun_dq_checks()\\n· DUPLICATE_ROW\\n· PK_DUPLICATE\\n· DATATYPE_VIOLATION", fillcolor="#bbf7d0", color="#15803d"]
    s6 [label="6  MAP\\napply_sheet_config()\\n· column rename\\n· static col inject\\n· in-batch dedup", fillcolor="#bbf7d0", color="#15803d"]
    s7 [label="7  WRITE\\nwrite_curated()\\nwrite_csv()", fillcolor="#bbf7d0", color="#15803d"]

    // Outputs
    pg_raw [label="raw.*\\n(Postgres TEXT)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    pg_err [label="error.dq_rejected_rows\\n(Postgres JSONB)\\n+ DQ report CSV", shape=cylinder, fillcolor="#fca5a5", color="#dc2626"]
    pg_cur [label="curated.*\\n(Postgres typed)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    csv    [label="downstream/*.csv\\n(clean flat files)", shape=note, fillcolor="#fef08a", color="#ca8a04"]

    // Config side-note
    cfg [label="config/ingestion.json\\n· file patterns\\n· column_map\\n· pk_column\\n· dq_rules\\n· write_mode", shape=note, fillcolor="#e0e7ff", color="#4338ca"]

    // Flow
    xlsx -> s1 -> s2 -> s3 -> s4 -> s5 -> s6 -> s7

    s3 -> pg_raw  [label=" Stage 3 output", color="#ca8a04"]
    s5 -> pg_err  [label=" rejected rows", color="#dc2626", style=dashed]
    s7 -> pg_cur  [label=" clean rows", color="#ca8a04"]
    s7 -> csv     [label=" append / overwrite", color="#ca8a04"]

    cfg -> s3 [style=dashed, color="#4338ca", label=" table name"]
    cfg -> s6 [style=dashed, color="#4338ca", label=" column_map"]
    cfg -> s7 [style=dashed, color="#4338ca", label=" write_mode"]
}
"""
    st.graphviz_chart(ingest_dot, use_container_width=True)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Stage details")
        stages = {
            "1 READ": "Opens xlsx, skips empty/ghost sheets, auto-detects header row by finding the first row with ≥ 50% non-null cells",
            "2 ARCHIVE": "Copies the original file to `data/archive/{YYYY-MM-DD}/` before any mutation — the audit copy is always there",
            "3 RAW WRITE": "Inserts every row into `raw.*` as TEXT with no coercion. This is the immutable source of truth.",
            "4 CLEAN": "Lowercase column names, map null markers (NULL, N/A, nan…) to NaN, coerce numeric and date columns, strip whitespace",
            "5 DQ CHECK": "Three checks: duplicate rows (all cols identical), PK duplicates (same key, different data), datatype violations (e.g. text in a numeric field)",
            "6 MAP": "Applies `column_map` from config to rename source → canonical names, injects static columns (e.g. `source_system=POS`), deduplicates within the batch",
            "7 WRITE": "Inserts clean rows into the `curated.*` Postgres table (ON CONFLICT DO NOTHING for fact tables) and writes the downstream CSV",
        }
        for stage, detail in stages.items():
            with st.expander(stage):
                st.write(detail)

    with col2:
        st.markdown("##### DQ check types")
        st.markdown("""
| Check | Trigger | Action |
|---|---|---|
| `DUPLICATE_ROW` | All column values identical to a prior row in the batch | Keep first, drop rest |
| `PK_DUPLICATE` | Same primary-key value, different data (retry / corruption) | Keep first, drop rest |
| `DATATYPE_VIOLATION` | Numeric column contains text, or value fails `positive_numeric` rule | Remove row |
""")
        st.markdown("##### Config controls every routing decision")
        st.code(
            """{
  "name": "pos_history",
  "file_pattern": "*pos*.xlsx",
  "sheets": [{
    "sheet": "Sales",
    "raw_table": "raw.pos_transactions",
    "curated_table": "curated.sales_transactions",
    "target_csv": "sales_transactions.csv",
    "pk_column": "transaction_id",
    "write_mode": "append",
    "column_map": { "ts": "transaction_ts", ... }
  }]
}""",
            language="json",
        )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — FORECASTING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
with tab_forecast:
    st.subheader("Forecasting Engine — Prophet Architecture")
    st.markdown(
        "One Facebook Prophet model per `(category, region)` pair — "
        "**20 independent models** (5 categories × 4 regions). "
        "Results land in Postgres and are served by the API."
    )

    forecast_dot = """
digraph Forecast {
    graph [rankdir=TB, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.5, ranksep=0.6]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.15,0.10"]
    edge  [fontname="Arial", fontsize=9, color="#64748b"]

    // Input CSVs
    sales [label="sales_transactions.csv", shape=note, fillcolor="#bfdbfe", color="#2563eb"]
    prod  [label="dim_product.csv\\nSKU → category", shape=note, fillcolor="#bfdbfe", color="#2563eb"]
    store [label="dim_store.csv\\nstore_id → region", shape=note, fillcolor="#bfdbfe", color="#2563eb"]
    cal   [label="seasonal_calendar.csv\\nUS holidays", shape=note, fillcolor="#bfdbfe", color="#2563eb"]
    promo [label="promo_windows.csv\\ndiscount schedules", shape=note, fillcolor="#bfdbfe", color="#2563eb"]

    // Build series
    join  [label="build_daily_series()\\n· join via dim_product + dim_store\\n· derive Online revenue:\\n  unit_price × quantity\\n· groupby(ds, category, region)\\n  → y = sum(revenue)", fillcolor="#bbf7d0", color="#15803d"]

    // Feature engineering
    hol   [label="build_holidays()\\nProphet holiday DataFrame\\nlower_window=0\\nupper_window=1 (post-holiday spend)", fillcolor="#e9d5ff", color="#7c3aed"]
    prom  [label="build_promo_feature()\\npromo_active = discount_pct / 100\\nmax wins on overlap\\n0.0 on non-promo days", fillcolor="#e9d5ff", color="#7c3aed"]

    // Skip guard
    skip  [label="n_unique_dates\\n< 60?", shape=diamond, fillcolor="#fef08a", color="#ca8a04"]
    skipped [label="SKIP\\n(log WARNING)", shape=oval, fillcolor="#fca5a5", color="#dc2626"]

    // Prophet fit
    fit   [label="Prophet.fit()\\n· weekly_seasonality=True\\n· yearly_seasonality=True\\n· seasonality_mode=multiplicative\\n· interval_width=0.90\\n· changepoint_prior_scale=0.05\\n· add_regressor(promo_active, mode=multiplicative)", fillcolor="#e9d5ff", color="#7c3aed"]

    // Predict
    pred  [label="Prophet.predict()\\nmake_future_dataframe(periods=90)\\nclip yhat / bounds ≥ 0", fillcolor="#e9d5ff", color="#7c3aed"]

    // Output
    db    [label="forecast_results (Postgres)\\nDELETE + INSERT per\\n(run_date, category, region)\\n→ idempotent re-runs", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    api   [label="GET /forecast\\n→ Forecast UI page", fillcolor="#fed7aa", color="#c2410c"]

    // Flow
    sales -> join
    prod  -> join
    store -> join
    join  -> skip
    cal   -> hol
    promo -> prom

    skip -> skipped [label="yes", color="#dc2626"]
    skip -> fit     [label="no", color="#15803d"]
    hol  -> fit
    prom -> fit
    fit  -> pred -> db -> api
}
"""
    st.graphviz_chart(forecast_dot, use_container_width=True)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Why Facebook Prophet?")
        reasons = {
            "Multiplicative seasonality": "CPG revenue scales — promo lift on a $10K/day baseline is $1.5K, not a flat offset. Prophet's `multiplicative` mode matches this exactly.",
            "External regressors with future values": "Promotions and holidays are scheduled in advance. Prophet accepts future regressor values in the forecast frame; ARIMA cannot.",
            "Native weekly + yearly seasonality": "Day-of-week peaks (weekends) and annual patterns (Q4, summer) are both strong CPG signals and are decomposed separately.",
            "Calibrated 90% confidence intervals": "Used for safety-stock lower bounds in inventory planning.",
            "Handles missing days": "Store closures and data-feed gaps create holes in the daily series. Prophet handles sparse grids; ARIMA requires a continuous grid.",
            "Interpretable output": "The decomposition (trend + seasonality + holiday + promo) is explainable to business stakeholders.",
        }
        for title, detail in reasons.items():
            with st.expander(title):
                st.write(detail)

    with col2:
        st.markdown("##### Model configuration")
        st.markdown("""
| Parameter | Value | Reason |
|---|---|---|
| `weekly_seasonality` | `True` | Weekend sales peaks |
| `yearly_seasonality` | `True` | Q4, summer, holiday cycles |
| `seasonality_mode` | `multiplicative` | Amplitude scales with trend |
| `interval_width` | `0.90` | 90% credible interval |
| `changepoint_prior_scale` | `0.05` | Moderate trend flexibility |
| `changepoint_range` | `0.90` | Changepoints up to 90% of history |
| `min_history_days` | `60` | Minimum unique dates to fit |
""")
        st.markdown("##### Output table schema")
        st.markdown("""
`public.forecast_results`
- `run_date` — forecast vintage date
- `category` / `region` — segment key
- `target_date` — predicted date
- `predicted_revenue` — Prophet `yhat`
- `yhat_lower` / `yhat_upper` — 90% CI bounds
- `model_version` — `"prophet-v1"`
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — API & UI LAYER
# ─────────────────────────────────────────────────────────────────────────────
with tab_api:
    st.subheader("API & UI Layer")
    st.markdown(
        "FastAPI is the single access boundary between the UI and all data. "
        "The Streamlit UI talks only to FastAPI — it has no direct database or filesystem access."
    )

    api_dot = """
digraph API {
    graph [rankdir=LR, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.4, ranksep=0.9]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.15,0.10"]
    edge  [fontname="Arial", fontsize=9]

    // ── UI Pages ──────────────────────────────────────────────────────────────
    subgraph cluster_ui {
        label="Streamlit UI  (ui/)"
        style=rounded
        color="#67e8f9"
        bgcolor="#ecfeff"
        fontname="Arial"

        home  [label="🏠 Home", fillcolor="#a5f3fc", color="#0e7490"]
        dash  [label="📊 Dashboard", fillcolor="#a5f3fc", color="#0e7490"]
        fc    [label="📈 Forecast", fillcolor="#a5f3fc", color="#0e7490"]
        ai    [label="🤖 AI Insights", fillcolor="#a5f3fc", color="#0e7490"]
        dq    [label="🛡 DQ Reports", fillcolor="#a5f3fc", color="#0e7490"]
        loads [label="🔄 Data Loads", fillcolor="#a5f3fc", color="#0e7490"]
        dbx   [label="🗄 DB Explorer", fillcolor="#a5f3fc", color="#0e7490"]
        client [label="api_client.py\\none function per endpoint", shape=component, fillcolor="#cffafe", color="#0e7490"]

        home -> client
        dash -> client
        fc   -> client
        ai   -> client
        dq   -> client
        loads -> client
        dbx  -> client
    }

    // ── API Endpoints ─────────────────────────────────────────────────────────
    subgraph cluster_api {
        label="FastAPI  (src/api/)  — 11 endpoints"
        style=rounded
        color="#fb923c"
        bgcolor="#fff7ed"
        fontname="Arial"

        health  [label="GET /health", fillcolor="#fed7aa", color="#c2410c"]
        summary [label="GET /summary", fillcolor="#fed7aa", color="#c2410c"]
        quality [label="GET /quality", fillcolor="#fed7aa", color="#c2410c"]
        products [label="GET /products", fillcolor="#fed7aa", color="#c2410c"]
        forecast [label="GET /forecast", fillcolor="#fed7aa", color="#c2410c"]
        dqr     [label="GET /dq-reports\\nGET /dq-reports/{file}", fillcolor="#fed7aa", color="#c2410c"]
        db_ep   [label="GET /db/overview\\nGET /db/table", fillcolor="#fed7aa", color="#c2410c"]
        ingest  [label="POST /ingest", fillcolor="#fed7aa", color="#c2410c"]
        genbatch [label="POST /generate-batch", fillcolor="#fed7aa", color="#c2410c"]
        insights [label="POST /insights", fillcolor="#fed7aa", color="#c2410c"]
        ask     [label="POST /ask", fillcolor="#fed7aa", color="#c2410c"]
    }

    // ── Data sources ─────────────────────────────────────────────────────────
    subgraph cluster_data {
        label="Data Sources"
        style=rounded
        color="#fbbf24"
        bgcolor="#fffbeb"
        fontname="Arial"

        csvs2   [label="downstream/*.csv\\n(9 files)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        pg_fc   [label="forecast_results\\n(Postgres)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        pg_audit [label="load_batch\\ndata_quality_log\\n(Postgres)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        pg_all  [label="raw.* curated.* error.*\\n(Postgres — DB Explorer only)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        qr_dir  [label="quality_reports/*.csv", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    }

    // ── LLM ──────────────────────────────────────────────────────────────────
    ollama2 [label="Ollama LLM\\n(local · offline)\\nfallback if unreachable", fillcolor="#fce7f3", color="#be185d",
             style="rounded,filled,dashed"]

    // ── Edges: UI → API ───────────────────────────────────────────────────────
    client -> health    [color="#0e7490"]
    client -> summary   [color="#0e7490"]
    client -> quality   [color="#0e7490"]
    client -> products  [color="#0e7490"]
    client -> forecast  [color="#0e7490"]
    client -> dqr       [color="#0e7490"]
    client -> db_ep     [color="#0e7490"]
    client -> ingest    [color="#0e7490"]
    client -> genbatch  [color="#0e7490"]
    client -> insights  [color="#0e7490"]
    client -> ask       [color="#0e7490"]

    // ── Edges: API → Data ─────────────────────────────────────────────────────
    summary  -> csvs2   [color="#ca8a04"]
    products -> csvs2   [color="#ca8a04"]
    forecast -> pg_fc   [color="#ca8a04"]
    quality  -> pg_audit [color="#ca8a04"]
    dqr      -> qr_dir  [color="#ca8a04"]
    db_ep    -> pg_all  [color="#ca8a04"]
    ingest   -> csvs2   [color="#ca8a04", style=dashed, label=" triggers pipeline"]
    insights -> csvs2   [color="#ca8a04"]
    ask      -> csvs2   [color="#ca8a04"]

    insights -> ollama2 [color="#be185d", style=dashed]
    ask      -> ollama2 [color="#be185d", style=dashed]
}
"""
    st.graphviz_chart(api_dot, use_container_width=True)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### API design rules")
        st.markdown("""
- All data access lives in `src/api/queries.py` — routes are thin
- Raw transaction rows are **never** sent to the LLM — only pre-aggregated context (< 1,000 tokens)
- Both `/insights` and `/ask` return deterministic fallback responses when Ollama is unreachable
- Schema is validated against an allowlist before any SQL execution (injection prevention)
- Table names in `/db/table` are verified against `information_schema` before interpolation
""")
    with col2:
        st.markdown("##### Endpoint groups")
        st.markdown("""
| Group | Endpoints | Purpose |
|---|---|---|
| Health | `/health` | Liveness + DB check |
| Analytics | `/summary`, `/quality`, `/products` | Revenue + DQ KPIs |
| Forecast | `/forecast` | Prophet predictions |
| Operations | `/ingest`, `/generate-batch` | Pipeline triggers |
| AI | `/insights`, `/ask` | LLM narrative + Q&A |
| DB Explorer | `/db/overview`, `/db/table` | Schema + live data |
| DQ Reports | `/dq-reports`, `/dq-reports/{file}` | Violation files |
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — CONTAINERISATION
# ─────────────────────────────────────────────────────────────────────────────
with tab_container:
    st.subheader("Containerisation — Docker Compose")
    st.markdown(
        "`docker compose up --build` starts the full stack. "
        "Services start in dependency order enforced by `healthcheck` + `depends_on`."
    )

    container_dot = """
digraph Docker {
    graph [rankdir=TB, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.6, ranksep=0.7]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.15,0.10"]
    edge  [fontname="Arial", fontsize=9]

    // ── Services ──────────────────────────────────────────────────────────────
    pg   [label="postgres\\nimage: postgres:16-alpine\\nport: 5432\\nvolume: pg_data\\ninit: db/init/01_schema.sql",
          fillcolor="#fef08a", color="#ca8a04"]

    oll  [label="ollama\\nimage: ollama/ollama\\nport: 11434\\nvolume: ollama_data\\n(model weights cached)",
          fillcolor="#fce7f3", color="#be185d"]

    init [label="ollama-init\\nimage: ollama/ollama\\nruns once · pulls model\\nthen exits",
          fillcolor="#fce7f3", color="#be185d", style="rounded,filled,dashed"]

    api  [label="api\\nbuild: Dockerfile.api\\nport: 8000\\nvolume: ./data (bind)\\nvolume: ./config (bind, read-only)\\nenv: DATABASE_URL + OLLAMA_BASE_URL",
          fillcolor="#fed7aa", color="#c2410c"]

    ui   [label="ui\\nbuild: Dockerfile.ui\\nport: 8501\\nenv: API_BASE_URL=http://api:8000\\nhealthcheck: /_stcore/health",
          fillcolor="#a5f3fc", color="#0e7490"]

    // ── Volumes ───────────────────────────────────────────────────────────────
    pg_vol  [label="pg_data\\n(named volume)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    oll_vol [label="ollama_data\\n(named volume, 4–5 GB)", shape=cylinder, fillcolor="#fce7f3", color="#be185d"]
    data_mnt [label="./data\\n(bind mount)", shape=cylinder, fillcolor="#e2e8f0", color="#475569"]

    // ── Startup order ─────────────────────────────────────────────────────────
    pg  -> api  [label=" depends_on (healthy)", color="#15803d"]
    oll -> api  [label=" depends_on (healthy)", color="#15803d"]
    oll -> init [label=" depends_on (healthy)", color="#be185d", style=dashed]
    api -> ui   [label=" depends_on (started)", color="#0e7490"]

    // ── Volume mounts ─────────────────────────────────────────────────────────
    pg  -> pg_vol   [style=dashed, label=" stores data", color="#ca8a04"]
    oll -> oll_vol  [style=dashed, label=" caches model", color="#be185d"]
    api -> data_mnt [style=dashed, label=" reads/writes", color="#475569"]
}
"""
    st.graphviz_chart(container_dot, use_container_width=True)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### One-command start")
        st.code(
            """# Full stack (first run — downloads Ollama model ~4.7 GB)
docker compose up --build

# First-time data setup (run once after stack is healthy)
docker compose exec api python3 scripts/generate_data.py
docker compose exec api python3 -m src.ingestion.pipeline
docker compose exec api python3 -m src.forecasting.forecaster""",
            language="bash",
        )
        st.markdown("##### Rebuild after code changes")
        st.code(
            """# Rebuild only the API image
docker compose up --build api

# Rebuild all
docker compose up --build""",
            language="bash",
        )

    with col2:
        st.markdown("##### Service table")
        st.markdown("""
| Service | Image / Build | Port | Purpose |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 | Database (schema auto-applied) |
| `ollama` | `ollama/ollama` | 11434 | Local LLM server |
| `ollama-init` | `ollama/ollama` | — | One-time model pull, then exits |
| `api` | `Dockerfile.api` | 8000 | FastAPI backend |
| `ui` | `Dockerfile.ui` | 8501 | Streamlit frontend |
""")
        st.markdown("##### Environment variable flow")
        st.markdown("""
`.env` file is loaded by all services via `env_file: .env`.
Docker Compose overrides three vars automatically:

- `DATABASE_URL` → `postgresql+psycopg2://cpg:…@postgres:5432/cpg_analytics`
- `OLLAMA_BASE_URL` → `http://ollama:11434/v1`
- `API_BASE_URL` → `http://api:8000`

Services reference each other by **service name** (not localhost) because they share the compose network.
""")

    st.info(
        "The `data/` directory is a **bind mount** — changes to Excel files and generated CSVs "
        "are immediately visible to the API container without a rebuild.",
        icon="ℹ️",
    )
