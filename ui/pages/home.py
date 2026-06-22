"""Home page — platform hub with quick stats and navigation cards."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import streamlit as st

import api_client

st.title("🛒 CPG Analytics Platform")
st.caption("End-to-end sales analytics: ingestion · data quality · forecasting · AI insights")
st.divider()

# ── Platform status ───────────────────────────────────────────────────────────

try:
    h = api_client.health()
    db_ok = h.get("db_connected", False)
    status = h.get("status", "unknown")
    if status == "ok":
        st.success(
            f"✅  API online  ·  DB {'connected' if db_ok else '⚠ disconnected'}  ·  v{h.get('version','')}",
            icon=None,
        )
    else:
        st.warning(f"⚠️  API degraded  ·  DB {'connected' if db_ok else 'disconnected'}")
except requests.exceptions.ConnectionError:
    st.error("❌  Cannot reach API — start it with:  `uvicorn src.api.main:app --port 8000`")
    st.stop()

st.divider()

# ── Quick stats ───────────────────────────────────────────────────────────────


@st.cache_data(ttl=60, show_spinner=False)
def _stats():
    try:
        s = api_client.get_summary()
        q = api_client.get_quality()
        d = api_client.get_dq_reports()
        return s, q, d
    except Exception:
        return None, None, None


summary, quality, dq = _stats()

c1, c2, c3, c4, c5 = st.columns(5)

if summary:
    c1.metric("💰 Total Revenue", f"${summary['total_revenue']:,.0f}")
    c2.metric("🧾 Transactions", f"{summary['transaction_count']:,}")
    c3.metric("🏆 Top Category", summary["top_category"])
else:
    c1.metric("💰 Total Revenue", "—")
    c2.metric("🧾 Transactions", "—")
    c3.metric("🏆 Top Category", "—")

if quality:
    c4.metric("🔍 DQ Issues (DB)", quality["total_issues"])
    c4.caption("from load_batch logs")
else:
    c4.metric("🔍 DQ Issues (DB)", "—")

if dq:
    c5.metric("🛡 DQ Report Files", dq["total"])
    c5.caption("pre-ingest violations")
else:
    c5.metric("🛡 DQ Report Files", "—")

st.divider()

# ── Navigation cards ──────────────────────────────────────────────────────────

st.subheader("Navigate to")

card_css = """
<style>
.nav-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 20px 16px 14px;
    text-align: center;
    min-height: 130px;
}
.nav-card h3 { margin: 0 0 6px; font-size: 1.1rem; }
.nav-card p  { margin: 0; color: #64748B; font-size: 0.85rem; }
</style>
"""
st.markdown(card_css, unsafe_allow_html=True)

row1 = st.columns(3)
row2 = st.columns(3)

with row1[0]:
    st.markdown(
        """<div class="nav-card">
        <h3>📊 Dashboard</h3>
        <p>Revenue KPIs · Category & region charts · Product performance · Data reliability</p>
    </div>""",
        unsafe_allow_html=True,
    )
    st.page_link("pages/dashboard.py", label="Open Dashboard →", use_container_width=True)

with row1[1]:
    st.markdown(
        """<div class="nav-card">
        <h3>📈 Forecast</h3>
        <p>Prophet predictions with confidence band · Category & region filters · Horizon slider</p>
    </div>""",
        unsafe_allow_html=True,
    )
    st.page_link("pages/forecast.py", label="Open Forecast →", use_container_width=True)

with row1[2]:
    st.markdown(
        """<div class="nav-card">
        <h3>🤖 AI Insights & Q&A</h3>
        <p>LLM narrative summary · Free-text questions answered from aggregated data</p>
    </div>""",
        unsafe_allow_html=True,
    )
    st.page_link("pages/insights.py", label="Open AI Insights →", use_container_width=True)

with row2[0]:
    st.markdown(
        """<div class="nav-card">
        <h3>🛡 DQ Reports</h3>
        <p>Browse pre-ingestion violation reports · Filter by check type · Inspect rejected rows</p>
    </div>""",
        unsafe_allow_html=True,
    )
    st.page_link("pages/dq_reports.py", label="Open DQ Reports →", use_container_width=True)

with row2[1]:
    st.markdown(
        """<div class="nav-card">
        <h3>🔄 Data Loads</h3>
        <p>Trigger historical or incremental ingest · View load_batch audit history</p>
    </div>""",
        unsafe_allow_html=True,
    )
    st.page_link("pages/data_loads.py", label="Open Data Loads →", use_container_width=True)

with row2[2]:
    st.markdown(
        """<div class="nav-card">
        <h3>📖 API Docs</h3>
        <p>FastAPI Swagger UI · All 9 endpoints · Try them live</p>
    </div>""",
        unsafe_allow_html=True,
    )
    import os

    api_base = os.environ.get("API_BASE_URL", "http://localhost:8000")
    st.link_button("Open API Docs →", url=f"{api_base}/docs", use_container_width=True)

st.divider()

# ── Recent DQ violations ──────────────────────────────────────────────────────

if dq and dq.get("reports"):
    st.subheader("🛡 Recent DQ Violations")
    import pandas as pd

    reports = dq["reports"][:5]  # latest 5
    rows = []
    for r in reports:
        for issue, cnt in r.get("by_issue", {}).items():
            rows.append(
                {
                    "Report": r["filename"],
                    "Source": r.get("source_file") or "—",
                    "Sheet": r.get("sheet") or "—",
                    "Issue": issue,
                    "Rejected": cnt,
                    "Run at": r.get("report_ts") or "—",
                }
            )
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No violations in recent reports.")
    st.page_link("pages/dq_reports.py", label="→ View all DQ reports")
elif dq is not None:
    st.info("No DQ violation reports yet — run an ingest to generate them.")

# ── Quick start reminder ──────────────────────────────────────────────────────

with st.expander("⚡ Quick start commands", expanded=False):
    st.code(
        """# 1. Generate synthetic data
python3 scripts/generate_data.py

# 2. Run historical ingestion (includes DQ checks → quality_reports/)
python3 -m src.ingestion.pipeline

# 3. Run forecaster (writes to Postgres)
python3 -m src.forecasting.forecaster

# 4. API  (already running if you see this page)
uvicorn src.api.main:app --reload --port 8000

# 5. UI
streamlit run ui/app.py""",
        language="bash",
    )
