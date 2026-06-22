"""
ui/pages/database.py

Database Explorer — browse schemas, tables, row counts, and live data.
"""

from __future__ import annotations

import sys
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parents[1]
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

import pandas as pd
import streamlit as st

import api_client

st.title("🗄️ Database Explorer")
st.caption("Browse schemas, tables and live data in Postgres (`cpg_analytics`)")

# ── Schema overview ───────────────────────────────────────────────────────────

st.subheader("Schema Overview")

with st.spinner("Loading schema…"):
    try:
        overview = api_client.get_db_overview()
    except Exception as exc:
        st.error(f"Could not connect to API: {exc}")
        st.stop()

schemas = overview.get("schemas", [])

if not schemas:
    st.warning("No tables found. Run the ingestion pipeline first.")
    st.stop()

# Build a flat summary table for the overview card
summary_rows = []
for schema in schemas:
    for tbl in schema["tables"]:
        summary_rows.append(
            {
                "Schema": tbl["schema_name"],
                "Table": tbl["table"],
                "Rows": tbl["row_count"],
            }
        )

summary_df = pd.DataFrame(summary_rows)

# Schema-level metrics in columns
schema_names = [s["schema_name"] for s in schemas]
cols = st.columns(len(schema_names))
for col, schema in zip(cols, schemas, strict=False):
    total = sum(t["row_count"] for t in schema["tables"])
    col.metric(
        label=f"`{schema['schema_name']}`",
        value=f"{total:,} rows",
        delta=f"{len(schema['tables'])} tables",
        delta_color="off",
    )

st.divider()

# Per-schema expandable sections
for schema in schemas:
    schema_name = schema["schema_name"]
    total_rows = sum(t["row_count"] for t in schema["tables"])

    _label_map = {
        "raw": "Raw layer — original TEXT data landed as-is from Excel",
        "curated": "Curated layer — typed, DQ-passed data ready for analytics",
        "error": "Error layer — rows rejected by the DQ gate (JSONB)",
        "public": "Public — audit tables (load_batch, data_quality_log, forecast_results)",
    }

    with st.expander(
        f"**{schema_name}** — {len(schema['tables'])} tables · {total_rows:,} rows",
        expanded=(schema_name in ("raw", "curated")),
    ):
        st.caption(_label_map.get(schema_name, ""))
        tbl_rows = [{"Table": t["table"], "Rows": t["row_count"]} for t in schema["tables"]]
        st.dataframe(
            pd.DataFrame(tbl_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rows": st.column_config.NumberColumn(format="%d"),
            },
        )

st.divider()

# ── Table data viewer ─────────────────────────────────────────────────────────

st.subheader("Table Data Viewer")

# Build (schema, table) options
table_options: list[tuple[str, str]] = []
for schema in schemas:
    for tbl in schema["tables"]:
        table_options.append((tbl["schema_name"], tbl["table"]))

option_labels = [f"{s}.{t}" for s, t in table_options]

c1, c2, c3 = st.columns([3, 1, 1])

with c1:
    selected_label = st.selectbox(
        "Select table",
        options=option_labels,
        index=0,
    )

selected_schema, selected_table = table_options[option_labels.index(selected_label)]
selected_meta = next(
    t
    for s in schemas
    for t in s["tables"]
    if t["schema_name"] == selected_schema and t["table"] == selected_table
)
total_rows = selected_meta["row_count"]

with c2:
    page_size = st.selectbox("Rows per page", [25, 50, 100, 250, 500], index=1)

with c3:
    max_pages = max(1, -(-total_rows // page_size))  # ceiling division
    page = st.number_input("Page", min_value=1, max_value=max_pages, value=1, step=1)

offset = (page - 1) * page_size

st.caption(
    f"**{selected_schema}.{selected_table}** — "
    f"{total_rows:,} total rows · showing {offset + 1}–{min(offset + page_size, total_rows)} "
    f"(page {page} of {max_pages})"
)

with st.spinner(f"Loading {selected_schema}.{selected_table}…"):
    try:
        result = api_client.get_db_table_data(
            schema=selected_schema,
            table=selected_table,
            limit=page_size,
            offset=offset,
        )
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        st.stop()

rows = result.get("rows", [])
columns = result.get("columns", [])

if not rows:
    st.info("No rows returned for this page.")
else:
    df = pd.DataFrame(rows, columns=columns)

    # Highlight metadata columns
    meta_cols = [c for c in df.columns if c.startswith("_")]
    biz_cols = [c for c in df.columns if not c.startswith("_")]

    tab_biz, tab_all = st.tabs(["Business columns", "All columns (incl. metadata)"])

    with tab_biz:
        if biz_cols:
            st.dataframe(df[biz_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No business columns in this table.")

    with tab_all:
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Download
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Download this page as CSV",
        data=csv,
        file_name=f"{selected_schema}_{selected_table}_page{page}.csv",
        mime="text/csv",
    )
