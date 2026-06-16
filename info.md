# CPG Analytics Platform

End-to-end analytics platform for CPG sales data: raw Excel → cleaned CSVs → Prophet forecasts → FastAPI → Streamlit dashboard with AI Q&A.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Data wrangling | pandas 2.x + openpyxl 3.x |
| Config | JSON (`config/ingestion.json`) |
| Settings / env | pydantic-settings 2.x |
| Logging | loguru |
| Database | PostgreSQL 16 (Docker) |
| ORM | SQLAlchemy 2.x |
| Forecasting | Prophet 1.x |
| API | FastAPI 0.137+ |
| UI | Streamlit 1.35+ |
| LLM | DeepSeek chat completions (optional; fallback built-in) |
| HTTP client | httpx (API→LLM), requests (UI→API) |
| Charts | Altair 5.x |
| Containerisation | Docker + docker-compose |

---

## Repository Layout

```
cpg-analytics/
├── config/
│   └── ingestion.json          ← all file/sheet routing rules (no Python hardcoding)
├── data/
│   ├── input/
│   │   ├── historical/         ← bulk Excel files (run once)
│   │   └── incremental/        ← daily/weekly batch files
│   └── output/
│       └── downstream/         ← 9 output CSVs written by the pipeline
├── db/
│   └── init/
│       └── 01_schema.sql       ← Postgres DDL (auto-applied by Docker on first start)
├── scripts/
│   └── generate_data.py        ← synthetic data generator (seed=42, deterministic)
├── src/
│   ├── common/
│   │   ├── config.py           ← Settings (all env vars via pydantic-settings)
│   │   ├── db.py               ← SQLAlchemy engine + get_session() context manager
│   │   └── excel_io.py         ← .xlsx reader: ghost-sheet skip + header auto-detect
│   ├── ingestion/
│   │   ├── config_loader.py    ← loads ingestion.json → typed dataclasses
│   │   └── pipeline.py         ← read → clean → write CSV (3-stage orchestration)
│   ├── forecasting/
│   │   └── forecaster.py       ← Prophet fits per (category, region); writes to DB
│   └── api/
│       ├── main.py             ← FastAPI app + lifespan
│       ├── models.py           ← all Pydantic response models
│       ├── queries.py          ← data access: reads CSVs + queries DB
│       ├── llm.py              ← DeepSeek client + deterministic fallback
│       └── routes/
│           ├── health.py       ← GET /health
│           ├── ingest.py       ← POST /ingest
│           ├── summary.py      ← GET /summary
│           ├── quality.py      ← GET /quality
│           ├── forecast.py     ← GET /forecast
│           ├── insights.py     ← POST /insights
│           └── ask.py          ← POST /ask
├── ui/
│   ├── app.py                  ← Streamlit entry point + st.navigation
│   ├── api_client.py           ← thin requests wrapper (reads API_BASE_URL)
│   └── pages/
│       ├── dashboard.py        ← revenue KPIs + charts + quality panel
│       ├── forecast.py         ← Prophet forecast chart with confidence band
│       ├── insights.py         ← LLM narrative + free-text Q&A
│       └── data_loads.py       ← trigger ingest + view audit results
├── Dockerfile.api              ← API container (python:3.11-slim)
├── Dockerfile.ui               ← UI container (python:3.11-slim)
├── docker-compose.yml          ← postgres + api + ui (all start with `docker compose up`)
├── .env.example                ← all env vars with defaults
└── pyproject.toml
```

---

## End-to-End Data Flow

```
scripts/generate_data.py
        │
        ▼
data/input/historical/*.xlsx          data/input/incremental/*.xlsx
        │                                       │
        └───────────────┬───────────────────────┘
                        ▼
              config/ingestion.json
              (7 file groups: dir, pattern, sheet→csv routing)
                        │
                        ▼
           src/ingestion/pipeline.py
           Stage 1 — READ    excel_io.read_workbook()
           Stage 2 — CLEAN   clean_dataframe()
           Stage 3 — WRITE   write_csv()
                        │
                        ▼
           data/output/downstream/   ← 9 CSVs
           sales_transactions.csv    (~41k rows)
           dim_product / dim_store / dim_region / seasonal_calendar
           promo_windows / marketing_campaigns / competitor_prices
           product_updates
                        │
                        ▼
           src/forecasting/forecaster.py
           • join CSVs → daily (category, region) revenue series
           • Prophet fit per pair (weekly + yearly seasonality)
           • promo_active regressor (discount_pct/100)
           • holiday component from seasonal_calendar
           • writes 20 pairs × 90 days = 1,800 rows to Postgres
                        │
                        ▼
              [Postgres] forecast_results table
              + load_batch / data_quality_log (written by /ingest)
                        │
                        ▼
              src/api/main.py  (FastAPI)
              7 endpoints — reads CSVs + DB; never raw rows to LLM
                        │
                        ▼
              ui/app.py  (Streamlit)
              4 pages — talks ONLY to FastAPI via API_BASE_URL
```

---

## Layer Details

### 1. Data Generation (`scripts/generate_data.py`)

Creates all Excel input files. Run once before the pipeline.

```bash
python3 scripts/generate_data.py
```

Generates:
- `historical_data.xlsx` — 4 sheets: dim_region, dim_store, dim_product, seasonal_calendar
- `pos_sales_history.xlsx` / `online_sales_history.xlsx` — ~24 months of transactions
- `promo_windows.xlsx`, `marketing_campaigns.xlsx`, `competitor_prices.xlsx`
- 3 incremental batch files in `data/input/incremental/`

Revenue signal: `demand = base × trend × weekly_factor × Q4_lift × promo_factor × noise`. Online rows have no `amount` column — revenue is derived as `unit_price × quantity` at aggregation time.

---

### 2. Ingestion Pipeline (`src/ingestion/`)

**`config/ingestion.json`** — the only place that knows file names, sheet names, column maps. No hardcoding in Python.

**`config_loader.py`** — parses the JSON into typed dataclasses (`IngestionConfig`, `FileGroup`, `SheetConfig`). Uses stdlib `json` only.

**`pipeline.py`** — three stages per sheet:

| Stage | Function | What it does |
|---|---|---|
| READ | `excel_io.read_workbook()` | Opens xlsx, skips ghost sheets, auto-detects header row |
| CLEAN | `clean_dataframe()` | Lowercase cols, null markers, date parsing, numeric coercion (ID cols protected) |
| WRITE | `write_csv()` | Overwrite or append; append aligns schema so POS+ONLINE rows merge cleanly |

The 7 file groups and their outputs:

| Group | Reads from | Writes to | Mode |
|---|---|---|---|
| reference_dimensions | `historical_data.xlsx` | 4 dim CSVs | overwrite |
| promo_windows | `promo_windows.xlsx` | `promo_windows.csv` | overwrite |
| marketing_campaigns | `marketing_campaigns.xlsx` | `marketing_campaigns.csv` | overwrite |
| competitor_prices | `competitor_prices.xlsx` | `competitor_prices.csv` | overwrite |
| pos_history | `*pos*.xlsx` | `sales_transactions.csv` | overwrite |
| online_history | `*online*.xlsx` | `sales_transactions.csv` | append |
| incremental_batches | `data/input/incremental/*.xlsx` | `sales_transactions.csv` | append |

```bash
python3 -m src.ingestion.pipeline
python3 -m src.ingestion.pipeline --config config/ingestion.json --root .
```

---

### 3. Forecasting (`src/forecasting/forecaster.py`)

Fits one Prophet model per `(category, region)` pair and writes predictions to Postgres.

**What it does:**
1. Reads the 5 downstream CSVs, joins them, aggregates to daily revenue per pair
2. Builds a Prophet holiday DataFrame from `seasonal_calendar.csv`
3. Builds a `promo_active` regressor (0–1 scale) from `promo_windows.csv`
4. Fits Prophet with weekly + yearly seasonality in multiplicative mode
5. Forecasts a configurable horizon (default 90 days)
6. Deletes stale rows for `(run_date, category, region)` then inserts fresh predictions

**Output table:** `forecast_results` — columns: `run_date`, `category`, `region`, `target_date`, `predicted_revenue`, `yhat_lower`, `yhat_upper`, `model_version`

```bash
python3 -m src.forecasting.forecaster
python3 -m src.forecasting.forecaster --horizon 180 --min-history 60
```

Extension points (data ingested, not yet wired as regressors): `marketing_campaigns`, `competitor_prices`.

---

### 4. API (`src/api/`)

FastAPI service that the UI talks to exclusively. Reads from downstream CSVs and Postgres. Never sends raw rows to the LLM.

**`main.py`** — creates the FastAPI app, wires all routers, checks DB on startup.

**`models.py`** — Pydantic response models for every endpoint.

**`queries.py`** — all data access in one place: CSV joins, DB queries, bounded context builder for `/ask`.

**`llm.py`** — DeepSeek chat completions via `httpx`. Two prompts (`insights`, `ask`). Deterministic fallback for both when `DEEPSEEK_API_KEY` is blank.

**Endpoints:**

| Method | Path | What it returns |
|---|---|---|
| GET | `/health` | `{status, db_connected, version}` |
| POST | `/ingest?mode=historical\|incremental` | Runs pipeline; returns `load_batch` audit (inserted/deduped/rejected/…) |
| GET | `/summary` | Total revenue, top category/region, breakdowns; optional `start_date`/`end_date` |
| GET | `/quality` | Issue counts by type + action, latest load_batch from Postgres |
| GET | `/forecast` | Precomputed Prophet rows filtered by `category`, `region`, `horizon` |
| POST | `/insights` | Revenue aggregates sent to LLM → narrative summary (fallback if no key) |
| POST | `/ask` | `{question}` → bounded context built from aggregates → LLM answer (fallback if no key) |

```bash
uvicorn src.api.main:app --reload --port 8000
```

---

### 5. UI (`ui/`)

Streamlit multipage app. Reads `API_BASE_URL` env var (default `http://localhost:8000`). **Never connects to the database directly.**

**`app.py`** — entry point; sets page config and wires the 4 pages via `st.navigation`.

**`api_client.py`** — thin `requests` wrapper. One function per API endpoint.

**Pages:**

| Page | API calls | What the user sees |
|---|---|---|
| 📊 Dashboard | `/summary`, `/quality` | 4 KPI metrics, bar charts by category + region, data-reliability panel |
| 📈 Forecast | `/summary`, `/forecast` | Category/region dropdowns, horizon slider, Altair band chart |
| 🤖 AI Insights & Q&A | `/insights`, `/ask` | "Generate Summary" button, free-text question box, LLM/fallback badge |
| 🔄 Data Loads | `/ingest`, `/quality` | Historical + Incremental buttons, colour-coded audit table, pipeline history |

```bash
streamlit run ui/app.py
```

---

## How to Run

### Local (no Docker)

```bash
# 1. Install
cd cpg-analytics
cp .env.example .env
pip install -e ".[dev]"

# 2. Start Postgres
docker compose up postgres -d

# 3. Generate data
python3 scripts/generate_data.py

# 4. Run ingestion
python3 -m src.ingestion.pipeline

# 5. Run forecaster (writes to Postgres)
python3 -m src.forecasting.forecaster

# 6. Start API
uvicorn src.api.main:app --reload --port 8000

# 7. Start UI  (in a separate terminal)
streamlit run ui/app.py
```

Open: `http://localhost:8501` (UI) · `http://localhost:8000/docs` (API docs)

### Docker Compose (full stack)

```bash
docker compose up --build
```

Starts: `postgres` → `api` (depends on postgres healthy) → `ui` (depends on api).

Services: Postgres on `:5432`, API on `:8000`, UI on `:8501`.

---

## Environment Variables (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | Postgres host |
| `POSTGRES_PORT` | `5432` | Postgres port |
| `POSTGRES_DB` | `cpg_analytics` | Database name |
| `POSTGRES_USER` | `cpg` | DB user |
| `POSTGRES_PASSWORD` | `changeme` | DB password |
| `DATABASE_URL` | _(derived)_ | Override full DSN (set by docker-compose automatically) |
| `DEEPSEEK_API_KEY` | _(blank)_ | LLM key — leave blank to use deterministic fallback |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model name |
| `API_BASE_URL` | `http://localhost:8000` | UI → API base URL (set to `http://api:8000` in Docker) |
| `INGESTION_CONFIG` | `config/ingestion.json` | Path to ingestion config |
| `LOG_LEVEL` | `INFO` | Loguru level |

---

## Postgres Tables

| Table | Written by | Read by |
|---|---|---|
| `dim_region`, `dim_store`, `dim_product`, `seasonal_calendar`, `promo_windows`, `marketing_campaigns`, `competitor_prices`, `sales_transactions` | (schema only; data lives in CSVs) | — |
| `load_batch` | `/ingest` API endpoint | `/quality` endpoint, Dashboard |
| `data_quality_log` | (reserved for future DQ tracking) | `/quality` endpoint |
| `forecast_results` | `forecaster.py` | `/forecast` endpoint, Forecast page |

---

## Key Design Decisions

**CSVs as the data layer** — the ingestion pipeline writes CSVs, not DB rows. CSVs act as lightweight tables for the forecaster and API. This avoids a DB dependency for ingestion and makes the data inspectable with any spreadsheet tool.

**Config-driven ingestion** — every file name, sheet name, column map, and routing rule lives in `config/ingestion.json`. Adding a new data source requires editing JSON only, no Python changes.

**Precomputed forecasts** — Prophet fits run as a CLI job (`forecaster.py`), not on API request. The API serves from a DB table. This keeps the API fast and stateless.

**Bounded LLM context** — `/ask` builds a compact pre-aggregated text context (revenue by category/region/month, quality stats, forecast metadata) and instructs the LLM to answer only from that context. Raw transaction rows are never sent to the LLM.

**LLM fallback** — both `/insights` and `/ask` return useful, deterministic responses when `DEEPSEEK_API_KEY` is blank. The stack runs end-to-end with no LLM key required.
