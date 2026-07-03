import altair as alt
import pandas as pd
import streamlit as st

from config import DASHBOARD_COLORS
from lead_pages import (
    display_leads,
    filter_controls,
    filter_leads,
    numeric_series,
    search_dataframe,
    visible_leads,
)
from styles import format_cr, page_heading


def clean_dimension(df, column, empty_label="Unspecified"):
    if df.empty:
        return pd.Series(dtype=str)
    if column not in df.columns:
        return pd.Series([empty_label] * len(df), index=df.index)
    series = df[column].fillna("").astype(str).str.strip()
    return series.mask(series == "", empty_label)


def dashboard_metric_values(df, metric_name):
    if metric_name == "Pipeline Value":
        return numeric_series(df, "pipeline_value"), "Pipeline Rs. Cr"
    if metric_name == "Revenue Realised":
        return numeric_series(df, "revenue_realised"), "Revenue Rs. Cr"
    return pd.Series(1, index=df.index, dtype=float), "Leads"


def dashboard_grouped_data(df, dimension, metric_name, top_n, empty_label="Unspecified"):
    if df.empty:
        return pd.DataFrame(columns=["Segment", "Value", "Display"])

    values, metric_title = dashboard_metric_values(df, metric_name)
    work = pd.DataFrame({
        "Segment": clean_dimension(df, dimension, empty_label),
        "Value": values,
    })
    grouped = (
        work.groupby("Segment", as_index=False)["Value"]
        .sum()
        .sort_values("Value", ascending=False)
        .head(int(top_n))
    )
    if metric_title == "Leads":
        grouped["Display"] = grouped["Value"].astype(int).map(lambda value: f"{value:,}")
    else:
        grouped["Display"] = grouped["Value"].map(lambda value: format_cr(float(value)))
    return grouped


def dashboard_status_summary(df):
    if df.empty:
        return pd.DataFrame(columns=["Status", "Leads", "Pipeline Rs. Cr", "Revenue Rs. Cr", "Avg Pipeline"])

    work = pd.DataFrame({
        "Status": clean_dimension(df, "lead_status"),
        "Pipeline Rs. Cr": numeric_series(df, "pipeline_value"),
        "Revenue Rs. Cr": numeric_series(df, "revenue_realised"),
    })
    work["Leads"] = 1
    summary = (
        work.groupby("Status", as_index=False)
        .agg({
            "Leads": "sum",
            "Pipeline Rs. Cr": "sum",
            "Revenue Rs. Cr": "sum",
        })
        .sort_values(["Pipeline Rs. Cr", "Leads"], ascending=[False, False])
    )
    summary["Avg Pipeline"] = summary.apply(
        lambda row: round(float(row["Pipeline Rs. Cr"]) / int(row["Leads"]), 2) if int(row["Leads"]) else 0,
        axis=1,
    )
    return summary


def styled_bar_chart(data, dimension_title, metric_title):
    if data.empty:
        return None

    height = max(220, min(430, 34 * len(data)))
    hover = alt.selection_point(on="pointerover", fields=["Segment"], empty=False)
    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadiusEnd=5)
        .encode(
            y=alt.Y(
                "Segment:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelLimit=190, labelFontSize=12, labelColor="#17202a"),
            ),
            x=alt.X(
                "Value:Q",
                title=None,
                axis=alt.Axis(grid=True, labelFontSize=11, gridColor="#edf0f3"),
            ),
            color=alt.Color("Segment:N", legend=None, scale=alt.Scale(range=DASHBOARD_COLORS)),
            opacity=alt.condition(hover, alt.value(1), alt.value(0.78)),
            tooltip=[
                alt.Tooltip("Segment:N", title=dimension_title),
                alt.Tooltip("Display:N", title=metric_title),
            ],
        )
        .add_params(hover)
        .properties(height=height)
        .configure_view(stroke=None)
        .configure_axis(domainColor="#dfe4ea", tickColor="#dfe4ea")
    )
    return chart


def render_dashboard_chart(title, caption, chart):
    with st.container(border=True):
        st.markdown(f"#### {title}")
        if caption:
            st.caption(caption)
        if chart is None:
            st.info("No data available for this chart.")
        else:
            st.altair_chart(chart, use_container_width=True)


def render_dashboard(user_email, role, manager_state):
    page_heading("Tracker Dashboard", "Executive summary for the active access scope.")
    df = visible_leads(user_email, role, manager_state)
    d_state, d_city, d_status, d_category = filter_controls("dashboard")
    dfd = filter_leads(df, d_state, d_city, d_status, d_category)

    dashboard_search = st.text_input(
        "Dashboard Search",
        value="",
        placeholder="Search client, city, owner, status...",
        key="dashboard_search",
    )

    if dashboard_search:
        dfd = search_dataframe(dfd, dashboard_search)

    pipeline = float(numeric_series(dfd, "pipeline_value").sum())
    revenue = float(numeric_series(dfd, "revenue_realised").sum())
    avg_pipeline = round(pipeline / len(dfd), 2) if len(dfd) else 0
    status_series = dfd.get("lead_status", pd.Series(dtype=str)).fillna("").astype(str).str.lower() if not dfd.empty else pd.Series(dtype=str)
    won_count = int((status_series == "won").sum()) if not dfd.empty else 0
    conversion = round((won_count / len(dfd)) * 100, 1) if len(dfd) else 0
    active_states = int(clean_dimension(dfd, "state").nunique()) if not dfd.empty else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Leads", f"{len(dfd):,}")
    k2.metric("Pipeline Rs. Cr", format_cr(pipeline))
    k3.metric("Revenue Rs. Cr", format_cr(revenue))
    k4.metric("Avg Pipeline", format_cr(avg_pipeline))
    k5.metric("Won Conversion", f"{conversion}%")

    st.markdown(
        f'<p class="dashboard-note">Showing {len(dfd):,} leads across {active_states:,} states for the selected access scope.</p>',
        unsafe_allow_html=True,
    )

    if dfd.empty:
        st.info("No lead data matches the selected filters.")
        return

    status_count_data = dashboard_grouped_data(dfd, "lead_status", "Lead Count", 10)
    status_pipeline_data = dashboard_grouped_data(dfd, "lead_status", "Pipeline Value", 10)
    state_pipeline_data = dashboard_grouped_data(dfd, "state", "Pipeline Value", 10)
    owner_count_data = dashboard_grouped_data(dfd, "lead_shared_by", "Lead Count", 10, "Unassigned")
    category_pipeline_data = dashboard_grouped_data(dfd, "client_category", "Pipeline Value", 10)
    status_summary = dashboard_status_summary(dfd)

    top_left, top_right = st.columns(2)
    with top_left:
        render_dashboard_chart(
            "Lead Status",
            "How many leads are sitting in each status",
            styled_bar_chart(status_count_data, "Status", "Leads"),
        )
    with top_right:
        render_dashboard_chart(
            "Pipeline by Status",
            "Where the current pipeline value is concentrated",
            styled_bar_chart(status_pipeline_data, "Status", "Pipeline Rs. Cr"),
        )

    left, right = st.columns(2)
    with left:
        render_dashboard_chart(
            "State Performance",
            "States ranked by pipeline value",
            styled_bar_chart(state_pipeline_data, "State", "Pipeline Rs. Cr"),
        )
        render_dashboard_chart(
            "Client Category",
            "Categories ranked by pipeline value",
            styled_bar_chart(category_pipeline_data, "Category", "Pipeline Rs. Cr"),
        )
    with right:
        render_dashboard_chart(
            "Source Owner",
            "Owners ranked by lead volume",
            styled_bar_chart(owner_count_data, "Owner", "Leads"),
        )
        with st.container(border=True):
            st.markdown("#### Status Summary")
            st.caption("Count, pipeline, revenue, and average value by status")
            st.dataframe(
                status_summary,
                use_container_width=True,
                hide_index=True,
                height=220,
                column_config={
                    "Status": st.column_config.TextColumn("Status", width="medium"),
                    "Leads": st.column_config.NumberColumn("Leads", format="%d"),
                    "Pipeline Rs. Cr": st.column_config.NumberColumn("Pipeline Rs. Cr", format="%.2f"),
                    "Revenue Rs. Cr": st.column_config.NumberColumn("Revenue Rs. Cr", format="%.2f"),
                    "Avg Pipeline": st.column_config.NumberColumn("Avg Pipeline", format="%.2f"),
                },
            )

    st.markdown("#### High Value Pipeline")
    top_pipeline = dfd.copy()
    if "pipeline_value" in top_pipeline.columns:
        top_pipeline["pipeline_value"] = pd.to_numeric(top_pipeline["pipeline_value"], errors="coerce").fillna(0)
        top_pipeline["revenue_realised"] = pd.to_numeric(top_pipeline.get("revenue_realised", 0), errors="coerce").fillna(0)
        top_pipeline = top_pipeline.sort_values("pipeline_value", ascending=False).head(12)
    st.dataframe(
        display_leads(top_pipeline),
        use_container_width=True,
        hide_index=True,
        height=390,
        column_config={
            "Pipeline Rs. Cr": st.column_config.NumberColumn("Pipeline Rs. Cr", format="%.2f"),
            "Revenue Rs. Cr": st.column_config.NumberColumn("Revenue Rs. Cr", format="%.2f"),
        },
    )
