"""Page — DQ Reports: browse pre-ingestion violation CSV files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt
import pandas as pd
import requests
import streamlit as st

import api_client

st.title("🛡 Data Quality Reports")
st.caption(
    "Pre-ingestion DQ violations captured by `src/dq/checker.py` before each sheet "
    "reaches the ingestion pipeline. Rejected rows are removed from clean data and stored here."
)
st.divider()

# ── Fetch report list ─────────────────────────────────────────────────────────


@st.cache_data(ttl=30, show_spinner=False)
def fetch_report_list():
    return api_client.get_dq_reports()


try:
    with st.spinner("Loading report index…"):
        report_list = fetch_report_list()
except requests.exceptions.ConnectionError:
    st.error("Cannot reach API. Is the server running?")
    st.stop()
except requests.exceptions.HTTPError as e:
    st.error(f"API error {e.response.status_code}: {e.response.text[:200]}")
    st.stop()

reports = report_list.get("reports", [])
total_files = report_list.get("total", 0)

# ── Summary header ────────────────────────────────────────────────────────────

h1, h2, h3 = st.columns(3)
total_rejected = sum(r["total_rejected"] for r in reports)
h1.metric("Report Files", total_files)
h2.metric("Total Rejected Rows", f"{total_rejected:,}")

# aggregate issue counts across all reports
all_issues: dict[str, int] = {}
for r in reports:
    for issue, cnt in r.get("by_issue", {}).items():
        all_issues[issue] = all_issues.get(issue, 0) + cnt

if all_issues:
    dominant = max(all_issues, key=lambda k: all_issues[k])
    h3.metric("Most Common Issue", dominant, help=f"{all_issues[dominant]:,} occurrences")
else:
    h3.metric("Most Common Issue", "—")

if not reports:
    st.info(
        "No DQ report files found in `data/output/quality_reports/`.  "
        "Run an ingest (via **Data Loads** page or `POST /ingest`) to generate them."
    )
    st.stop()

st.divider()

# ── Overview chart ────────────────────────────────────────────────────────────

if all_issues:
    st.subheader("Violations by Check Type (all reports)")
    df_issues = pd.DataFrame([{"Issue": k, "Count": v} for k, v in all_issues.items()]).sort_values(
        "Count", ascending=False
    )

    colour_map = {
        "DUPLICATE_ROW": "#EF4444",
        "PK_DUPLICATE": "#F97316",
        "DATATYPE_VIOLATION": "#EAB308",
    }

    chart = (
        alt.Chart(df_issues)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            x=alt.X("Count:Q", title="Rejected rows"),
            y=alt.Y("Issue:N", sort="-x", title=""),
            color=alt.Color(
                "Issue:N",
                scale=alt.Scale(
                    domain=list(colour_map.keys()),
                    range=list(colour_map.values()),
                ),
                legend=None,
            ),
            tooltip=["Issue:N", "Count:Q"],
        )
        .properties(height=max(80, len(df_issues) * 40))
    )
    st.altair_chart(chart, use_container_width=True)

st.divider()

# ── Report index table ────────────────────────────────────────────────────────

st.subheader("Report Files")

index_rows = []
for r in reports:
    index_rows.append(
        {
            "Filename": r["filename"],
            "Run at": r.get("report_ts") or "—",
            "Source file": r.get("source_file") or "—",
            "Sheet": r.get("sheet") or "—",
            "Rejected": r["total_rejected"],
            "DUP_ROW": r["by_issue"].get("DUPLICATE_ROW", 0),
            "PK_DUP": r["by_issue"].get("PK_DUPLICATE", 0),
            "DTYPE": r["by_issue"].get("DATATYPE_VIOLATION", 0),
        }
    )

df_index = pd.DataFrame(index_rows)


def _colour_rejected(val):
    if isinstance(val, int) and val > 0:
        return "background-color: #FEF2F2; color: #991B1B"
    return ""


st.dataframe(
    df_index.style.map(_colour_rejected, subset=["Rejected", "DUP_ROW", "PK_DUP", "DTYPE"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ── Row-level drill-down ──────────────────────────────────────────────────────

st.subheader("Inspect Rejected Rows")

filenames = [r["filename"] for r in reports]
selected = st.selectbox(
    "Select a report file to inspect",
    options=filenames,
    index=0,
    help="Files are sorted newest-first",
)

issue_filter = st.multiselect(
    "Filter by issue type",
    options=["DUPLICATE_ROW", "PK_DUPLICATE", "DATATYPE_VIOLATION"],
    default=[],
    placeholder="All issue types",
)

load_btn = st.button("Load Report", type="primary")

if load_btn or f"dq_detail_{selected}" in st.session_state:
    if load_btn:
        try:
            with st.spinner("Fetching report rows…"):
                detail = api_client.get_dq_report_detail(selected)
            st.session_state[f"dq_detail_{selected}"] = detail
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot reach the API. Is the server running?")
            st.stop()
        except requests.exceptions.Timeout:
            st.error("❌ Request timed out loading the report.")
            st.stop()
        except requests.exceptions.HTTPError as e:
            st.error(f"❌ API error {e.response.status_code}: {e.response.text[:200]}")
            st.stop()
        except Exception as e:
            st.error(f"❌ {type(e).__name__}: {e}")
            st.stop()

    detail = st.session_state.get(f"dq_detail_{selected}")
    if not detail:
        st.stop()

    rows_data = detail.get("rows", [])
    total_rows = detail.get("total", len(rows_data))

    if not rows_data:
        st.info("No rows in this report.")
        st.stop()

    df_rows = pd.DataFrame(rows_data)

    # Apply issue filter
    if issue_filter and "_dq_issue" in df_rows.columns:
        df_rows = df_rows[df_rows["_dq_issue"].isin(issue_filter)]

    m1, m2 = st.columns(2)
    m1.metric("Total rows in report", total_rows)
    m2.metric("Showing", len(df_rows))

    # Highlight DQ meta columns
    dq_cols = [c for c in df_rows.columns if c.startswith("_dq_")]
    data_cols = [c for c in df_rows.columns if not c.startswith("_dq_")]
    display_cols = dq_cols + data_cols  # DQ context first

    def _hl_issue(val):
        colours = {
            "DUPLICATE_ROW": "#FEE2E2",
            "PK_DUPLICATE": "#FFEDD5",
            "DATATYPE_VIOLATION": "#FEF9C3",
        }
        return f"background-color: {colours.get(val, '#F8FAFC')}"

    styled = df_rows[display_cols].style
    if "_dq_issue" in df_rows.columns:
        styled = styled.map(_hl_issue, subset=["_dq_issue"])

    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Download button
    csv_bytes = df_rows[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Download filtered rows as CSV",
        data=csv_bytes,
        file_name=f"filtered_{selected}",
        mime="text/csv",
    )
