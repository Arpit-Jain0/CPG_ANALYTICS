"""Page — Architecture & Data Flow."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.title("🏗️ Architecture & Data Flow")
st.caption(
    "End-to-end view of the CPG Analytics platform — from raw Excel files through "
    "ingestion, forecasting, and API to the Streamlit dashboard."
)
st.divider()

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
    st.subheader("Full Platform — End to End")
    st.markdown(
        "Data flows left to right: raw Excel files → ingestion pipeline → "
        "database tables → forecasting → API → UI."
    )

    combined_dot = """
digraph CPG {
    graph [rankdir=LR, splines=ortho, bgcolor="#f8fafc", pad=0.6, nodesep=0.6, ranksep=0.9]
    node  [fontname="Arial", fontsize=11, style="rounded,filled", margin="0.18,0.12"]
    edge  [fontname="Arial", fontsize=9, color="#64748b"]

    subgraph cluster_sources {
        label="Data Sources"
        style=rounded
        color="#93c5fd"
        bgcolor="#eff6ff"
        fontname="Arial"
        fontsize=12
        hist [label="Historical Excel Files", fillcolor="#bfdbfe", color="#2563eb"]
        incr [label="Incremental Excel Batches", fillcolor="#bfdbfe", color="#2563eb"]
    }

    subgraph cluster_pipeline {
        label="Ingestion Pipeline"
        style=rounded
        color="#6ee7b7"
        bgcolor="#f0fdf4"
        fontname="Arial"
        fontsize=12
        pipe [label="7-Stage Pipeline\lRead · Clean · DQ Check\lMap · Write", fillcolor="#bbf7d0", color="#15803d"]
    }

    subgraph cluster_storage {
        label="Storage"
        style=rounded
        color="#fbbf24"
        bgcolor="#fffbeb"
        fontname="Arial"
        fontsize=12
        pg_raw [label="Raw Tables\n(PostgreSQL)", fillcolor="#fef08a", color="#ca8a04"]
        pg_cur [label="Curated Tables\n(PostgreSQL)", fillcolor="#fef08a", color="#ca8a04"]
        pg_err [label="Rejected Rows\n(PostgreSQL)", fillcolor="#fca5a5", color="#dc2626"]
    }

    subgraph cluster_forecast {
        label="Forecasting"
        style=rounded
        color="#c4b5fd"
        bgcolor="#faf5ff"
        fontname="Arial"
        fontsize=12
        prophet [label="Prophet Models\nOne per category × region", fillcolor="#e9d5ff", color="#7c3aed"]
        fc_tbl  [label="Forecast Results\n(PostgreSQL)", fillcolor="#e9d5ff", color="#7c3aed"]
    }

    subgraph cluster_api {
        label="API"
        style=rounded
        color="#fb923c"
        bgcolor="#fff7ed"
        fontname="Arial"
        fontsize=12
        api [label="FastAPI Backend", fillcolor="#fed7aa", color="#c2410c"]
    }

    ollama [label="Ollama LLM\n(Local)", fillcolor="#fce7f3", color="#be185d", style="rounded,filled"]

    subgraph cluster_ui {
        label="Dashboard"
        style=rounded
        color="#67e8f9"
        bgcolor="#ecfeff"
        fontname="Arial"
        fontsize=12
        ui [label="Streamlit UI\nHome · Dashboard · Forecast\nAI Insights · DQ Reports\nData Loads · DB Explorer", fillcolor="#a5f3fc", color="#0e7490"]
    }

    hist -> pipe
    incr -> pipe

    pipe -> pg_raw [label=" raw"]
    pipe -> pg_cur [label=" clean"]
    pipe -> pg_err [label=" rejected", color="#dc2626"]

    pg_cur -> prophet
    prophet -> fc_tbl

    pg_cur -> api
    fc_tbl -> api
    ollama -> api

    api -> ui [label=" JSON"]
}
"""
    st.graphviz_chart(combined_dot, use_container_width=True)

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### Design principles")
        st.markdown("""
- UI reads only from the API — never directly from the database
- Raw rows are never sent to the LLM — only aggregated totals
- Every pipeline stage is independently testable
- Each layer can be replaced without changing the others
""")
    with c2:
        st.markdown("##### Data layers")
        st.markdown("""
- **Raw tables** — immutable copy of every ingested row as-is
- **Curated tables** — typed, validated, deduplicated records read by the API and forecaster
- **Rejected rows** — DQ violations stored separately for audit
- **Forecast results** — Prophet predictions stored and served via the API
""")
    with c3:
        st.markdown("##### Tech stack")
        st.markdown("""
- **Pipeline** — Python · pandas · openpyxl
- **Database** — PostgreSQL · SQLAlchemy
- **Forecasting** — Facebook Prophet
- **API** — FastAPI · Pydantic
- **Dashboard** — Streamlit · Altair
- **LLM** — Ollama · llama3.1
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — INGESTION PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
with tab_ingest:
    st.subheader("Ingestion Pipeline")
    st.markdown(
        "Every Excel file passes through seven ordered stages. "
        "Clean rows go to the curated database tables. "
        "Rejected rows are written to a quality report without touching the main tables."
    )

    ingest_dot = """
digraph Ingest {
    graph [rankdir=LR, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.5, ranksep=0.9]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.15,0.10"]
    edge  [fontname="Arial", fontsize=9]

    xlsx [label="Excel File\n(.xlsx)", shape=note, fillcolor="#bfdbfe", color="#2563eb"]

    s1 [label="1  READ\nOpen file\nDetect header row\nDiscover sheets", fillcolor="#bbf7d0", color="#15803d"]
    s2 [label="2  ARCHIVE\nCopy original file\nbefore any changes", fillcolor="#bbf7d0", color="#15803d"]
    s3 [label="3  RAW WRITE\nInsert all rows as-is\ninto raw tables", fillcolor="#bbf7d0", color="#15803d"]
    s4 [label="4  CLEAN\nFix date formats\nRepair nulls\nNormalise columns", fillcolor="#bbf7d0", color="#15803d"]
    s5 [label="5  DQ CHECK\nDuplicate rows\nDuplicate keys\nDatatype violations", fillcolor="#bbf7d0", color="#15803d"]
    s6 [label="6  MAP\nRename columns\nto canonical names\nDeduplicate batch", fillcolor="#bbf7d0", color="#15803d"]
    s7 [label="7  WRITE\nInsert into curated tables", fillcolor="#bbf7d0", color="#15803d"]

    pg_raw [label="Raw Tables\n(PostgreSQL)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    pg_err [label="Rejected Rows\n(PostgreSQL)\n+ DQ Report", shape=cylinder, fillcolor="#fca5a5", color="#dc2626"]
    pg_cur [label="Curated Tables\n(PostgreSQL)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]

    cfg [label="ingestion.json\nColumn mapping\nDQ rules\nWrite mode", shape=note, fillcolor="#e0e7ff", color="#4338ca"]

    xlsx -> s1 -> s2 -> s3 -> s4 -> s5 -> s6 -> s7

    s3 -> pg_raw [color="#ca8a04"]
    s5 -> pg_err [color="#dc2626", style=dashed, label=" rejected"]
    s7 -> pg_cur [color="#ca8a04"]

    cfg -> s4 [style=dashed, color="#4338ca"]
    cfg -> s6 [style=dashed, color="#4338ca"]
    cfg -> s7 [style=dashed, color="#4338ca"]
}
"""
    st.graphviz_chart(ingest_dot, use_container_width=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### What each stage does")
        st.markdown("""
| Stage | Purpose |
|---|---|
| **Read** | Opens the Excel file, finds the real header row, discovers all sheets |
| **Archive** | Saves a copy of the original file before any processing begins |
| **Raw Write** | Stores every row as-is in the raw database table — the immutable source of truth |
| **Clean** | Fixes mixed date formats, repairs null values, normalises column names |
| **DQ Check** | Runs three checks — duplicate rows, duplicate primary keys, datatype violations |
| **Map** | Renames source columns to canonical names using the config file, deduplicates within the batch |
| **Write** | Inserts clean rows into the curated table |
""")
    with col2:
        st.markdown("##### DQ checks")
        st.markdown("""
| Check | What triggers it | Action |
|---|---|---|
| Duplicate row | All column values match a prior row in the batch | Keep first, remove rest |
| PK duplicate | Same primary key, different data | Keep first, remove rest |
| Datatype violation | Text in a numeric column, invalid date, negative quantity | Remove row |
""")
        st.markdown("##### Configuration-driven routing")
        st.markdown("""
All routing decisions — which table, which columns, which DQ rules, which CSV to write —
are defined in `config/ingestion.json`.
Adding a new data source requires no code changes, only a new config entry.
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — FORECASTING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
with tab_forecast:
    st.subheader("Forecasting Engine")
    st.markdown(
        "Facebook Prophet trains one model per product category and region. "
        "Each model uses historical sales, promotion windows, and holiday calendars "
        "to generate a 90-day revenue prediction with a confidence band."
    )

    forecast_dot = """
digraph Forecast {
    graph [rankdir=TB, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.5, ranksep=0.7]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.15,0.10"]
    edge  [fontname="Arial", fontsize=9, color="#64748b"]

    subgraph cluster_inputs {
        label="Inputs"
        style=rounded
        color="#93c5fd"
        bgcolor="#eff6ff"
        fontname="Arial"
        fontsize=11

        sales [label="Sales Transactions\n(curated.sales_transactions)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        promo [label="Promotion Windows\n(curated.promo_windows)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        cal   [label="Holiday Calendar\n(curated.seasonal_calendar)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    }

    subgraph cluster_prep {
        label="Data Preparation"
        style=rounded
        color="#6ee7b7"
        bgcolor="#f0fdf4"
        fontname="Arial"
        fontsize=11

        series [label="Build Daily Revenue Series\nGroup by category and region", fillcolor="#bbf7d0", color="#15803d"]
        hol    [label="Build Holiday Features\nUS public holidays", fillcolor="#bbf7d0", color="#15803d"]
        prom   [label="Build Promo Features\nActive discount per day", fillcolor="#bbf7d0", color="#15803d"]
    }

    subgraph cluster_model {
        label="Prophet Model"
        style=rounded
        color="#c4b5fd"
        bgcolor="#faf5ff"
        fontname="Arial"
        fontsize=11

        fit  [label="Train Model\nWeekly + yearly seasonality\nPromo and holiday regressors\nMultiplicative mode", fillcolor="#e9d5ff", color="#7c3aed"]
        pred [label="Generate Forecast\n90-day horizon\n90% confidence interval", fillcolor="#e9d5ff", color="#7c3aed"]
    }

    db  [label="Forecast Results\n(PostgreSQL)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    api [label="GET /forecast\n→ Forecast page", fillcolor="#fed7aa", color="#c2410c"]

    sales -> series
    promo -> prom
    cal   -> hol

    series -> fit
    hol    -> fit
    prom   -> fit

    fit  -> pred -> db -> api
}
"""
    st.graphviz_chart(forecast_dot, use_container_width=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Why Prophet")
        st.markdown("""
| Requirement | How Prophet meets it |
|---|---|
| Weekly patterns | Built-in — captures weekend vs weekday lift automatically |
| Yearly patterns | Built-in — Q4 peaks, seasonal dips |
| Promotion windows | Accepts external regressors with future values |
| Holiday effects | Native holiday calendar support |
| Missing dates | Handles gaps in the daily series without imputation |
| Explainability | Decomposes trend, seasonality, and regressor effects separately |
""")
    with col2:
        st.markdown("##### Model settings")
        st.markdown("""
| Setting | Value |
|---|---|
| Seasonality mode | Multiplicative |
| Confidence interval | 90% |
| Weekly seasonality | Enabled |
| Yearly seasonality | Enabled |
| External regressors | Promotion windows, US holidays |
| Minimum history required | 60 days |
""")
        st.markdown("##### Output")
        st.markdown("""
Each model writes one row per forecast day to `forecast_results`:
- `target_date` — the predicted date
- `predicted_revenue` — point estimate
- `yhat_lower` / `yhat_upper` — 90% confidence bounds
- `category` / `region` — model segment
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — API & UI LAYER
# ─────────────────────────────────────────────────────────────────────────────
with tab_api:
    st.subheader("API & UI Layer")
    st.markdown(
        "FastAPI is the single access point between the dashboard and all data. "
        "The Streamlit UI talks only to the API — it has no direct database or file system access."
    )

    api_dot = """
digraph API {
    graph [rankdir=LR, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.4, ranksep=1.0]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.15,0.10"]
    edge  [fontname="Arial", fontsize=9]

    subgraph cluster_ui {
        label="Streamlit Dashboard"
        style=rounded
        color="#67e8f9"
        bgcolor="#ecfeff"
        fontname="Arial"

        home  [label="Home", fillcolor="#a5f3fc", color="#0e7490"]
        dash  [label="Dashboard", fillcolor="#a5f3fc", color="#0e7490"]
        fc    [label="Forecast", fillcolor="#a5f3fc", color="#0e7490"]
        ai    [label="AI Insights", fillcolor="#a5f3fc", color="#0e7490"]
        dq    [label="DQ Reports", fillcolor="#a5f3fc", color="#0e7490"]
        loads [label="Data Loads", fillcolor="#a5f3fc", color="#0e7490"]
        dbx   [label="DB Explorer", fillcolor="#a5f3fc", color="#0e7490"]
        client [label="api_client.py", shape=component, fillcolor="#cffafe", color="#0e7490"]

        home  -> client
        dash  -> client
        fc    -> client
        ai    -> client
        dq    -> client
        loads -> client
        dbx   -> client
    }

    subgraph cluster_api {
        label="FastAPI Backend"
        style=rounded
        color="#fb923c"
        bgcolor="#fff7ed"
        fontname="Arial"

        health   [label="GET /health", fillcolor="#fed7aa", color="#c2410c"]
        summary  [label="GET /summary", fillcolor="#fed7aa", color="#c2410c"]
        quality  [label="GET /quality", fillcolor="#fed7aa", color="#c2410c"]
        products [label="GET /products", fillcolor="#fed7aa", color="#c2410c"]
        forecast [label="GET /forecast", fillcolor="#fed7aa", color="#c2410c"]
        dqr      [label="GET /dq-reports", fillcolor="#fed7aa", color="#c2410c"]
        db_ep    [label="GET /db/overview\nGET /db/table", fillcolor="#fed7aa", color="#c2410c"]
        ingest   [label="POST /ingest", fillcolor="#fed7aa", color="#c2410c"]
        genbatch [label="POST /generate-batch", fillcolor="#fed7aa", color="#c2410c"]
        insights [label="POST /insights", fillcolor="#fed7aa", color="#c2410c"]
        ask      [label="POST /ask", fillcolor="#fed7aa", color="#c2410c"]
    }

    subgraph cluster_data {
        label="Data Sources"
        style=rounded
        color="#fbbf24"
        bgcolor="#fffbeb"
        fontname="Arial"

        pg_cur  [label="Curated Tables\n(PostgreSQL)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        pg_fc   [label="Forecast Results\n(PostgreSQL)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        pg_audit [label="Load Batches\nQuality Log\n(PostgreSQL)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        pg_all  [label="All Tables\n(PostgreSQL)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
        qr_dir  [label="Quality Reports\n(CSV files)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    }

    ollama [label="Ollama LLM", fillcolor="#fce7f3", color="#be185d", style="rounded,filled"]

    client -> health
    client -> summary
    client -> quality
    client -> products
    client -> forecast
    client -> dqr
    client -> db_ep
    client -> ingest
    client -> genbatch
    client -> insights
    client -> ask

    summary  -> pg_cur
    products -> pg_cur
    forecast -> pg_fc
    quality  -> pg_audit
    dqr      -> qr_dir
    db_ep    -> pg_all
    insights -> pg_cur
    ask      -> pg_cur

    insights -> ollama  [color="#be185d"]
    ask      -> ollama  [color="#be185d"]
}
"""
    st.graphviz_chart(api_dot, use_container_width=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Design rules")
        st.markdown("""
- All data access is in `src/api/queries.py` — routes stay thin
- Raw transaction rows are never sent to the LLM — only pre-aggregated context
- Table names in the DB Explorer are validated before any SQL runs
- Every endpoint returns a typed Pydantic response model
""")
    with col2:
        st.markdown("##### Endpoints by group")
        st.markdown("""
| Group | Endpoints |
|---|---|
| Health | `/health` |
| Analytics | `/summary` · `/quality` · `/products` |
| Forecast | `/forecast` |
| Operations | `/ingest` · `/generate-batch` |
| AI | `/insights` · `/ask` |
| DB Explorer | `/db/overview` · `/db/table` |
| DQ Reports | `/dq-reports` · `/dq-reports/{file}` |
""")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — CONTAINERISATION
# ─────────────────────────────────────────────────────────────────────────────
with tab_container:
    st.subheader("Containerisation — Docker Compose")
    st.markdown(
        "`docker compose up --build` starts all five services in dependency order. "
        "Each service waits for its dependency to be healthy before starting."
    )

    container_dot = """
digraph Docker {
    graph [rankdir=TB, splines=ortho, bgcolor="#f8fafc", pad=0.5, nodesep=0.6, ranksep=0.8]
    node  [fontname="Arial", fontsize=10, style="rounded,filled", margin="0.18,0.12"]
    edge  [fontname="Arial", fontsize=9]

    pg   [label="postgres\nDatabase\nPort 5432\nSchema auto-applied on first start",
          fillcolor="#fef08a", color="#ca8a04"]

    oll  [label="ollama\nLocal LLM Server\nPort 11434\nModel weights cached in volume",
          fillcolor="#fce7f3", color="#be185d"]

    init [label="ollama-init\nPulls the LLM model\nRuns once then exits",
          fillcolor="#fce7f3", color="#be185d", style="rounded,filled,dashed"]

    api  [label="api\nFastAPI Backend\nPort 8000\nReads data/ and config/ folders",
          fillcolor="#fed7aa", color="#c2410c"]

    ui   [label="ui\nStreamlit Dashboard\nPort 8501\nTalks to api service only",
          fillcolor="#a5f3fc", color="#0e7490"]

    pg_vol  [label="pg_data\n(named volume)", shape=cylinder, fillcolor="#fef08a", color="#ca8a04"]
    oll_vol [label="ollama_data\n(named volume)", shape=cylinder, fillcolor="#fce7f3", color="#be185d"]
    data_mnt [label="./data\n(bind mount)", shape=cylinder, fillcolor="#e2e8f0", color="#475569"]

    pg  -> api  [label=" postgres healthy → api starts", color="#15803d"]
    oll -> api  [label=" ollama started → api starts", color="#15803d"]
    oll -> init [label=" ollama healthy → pull model", color="#be185d", style=dashed]
    api -> ui   [label=" api started → ui starts", color="#0e7490"]

    pg  -> pg_vol   [style=dashed, color="#ca8a04"]
    oll -> oll_vol  [style=dashed, color="#be185d"]
    api -> data_mnt [style=dashed, color="#475569"]
}
"""
    st.graphviz_chart(container_dot, use_container_width=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Commands")
        st.code(
            """# Start the full stack
docker compose up --build

# Load data (run once after stack is healthy)
docker compose exec api python3 scripts/generate_data.py
docker compose exec api python3 -m src.ingestion.pipeline --mode historical
docker compose exec api python3 -m src.ingestion.pipeline --mode incremental
docker compose exec api python3 -m src.forecasting.forecaster

# Rebuild a single service after code changes
docker compose up --build api
docker compose up --build ui""",
            language="bash",
        )

    with col2:
        st.markdown("##### Services")
        st.markdown("""
| Service | Port | Purpose |
|---|---|---|
| `postgres` | 5432 | Database — schema applied on first boot |
| `ollama` | 11434 | Runs the local LLM server |
| `ollama-init` | — | Pulls the LLM model once then exits |
| `api` | 8000 | FastAPI backend |
| `ui` | 8501 | Streamlit dashboard |
""")
        st.markdown("##### Service communication")
        st.markdown("""
Services reference each other by service name — not `localhost`.
The `.env` file is shared across all services.
Key variables set automatically by Compose:

- `DATABASE_URL` → points to the `postgres` service
- `OLLAMA_BASE_URL` → points to the `ollama` service
- `API_BASE_URL` → points to the `api` service
""")
