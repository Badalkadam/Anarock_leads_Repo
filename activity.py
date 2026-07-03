import pandas as pd
import streamlit as st

from config import CACHE_TTL_SECONDS
from db import db_execute
from lead_pages import visible_leads
from styles import page_heading


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def read_activity_log(limit=500):
    query = "SELECT * FROM activity_log ORDER BY changed_on DESC LIMIT %s;"
    results = db_execute(query, [limit], fetch_all=True)
    return pd.DataFrame(results) if results else pd.DataFrame()


def render_activity(user_email, role, manager_state):
    page_heading("Activity Log", "Recent change history for accessible opportunities.")
    log_df = read_activity_log(500)
    if role != "admin" and not log_df.empty:
        visible_df = visible_leads(user_email, role, manager_state)
        visible_opps = set(visible_df["opportunity_id"].dropna().astype(str).tolist()) if not visible_df.empty else set()
        log_df = log_df[log_df["opportunity_id"].astype(str).isin(visible_opps)]

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        opp_filter = st.text_input("Opportunity ID")
    with c2:
        action_options = [""] + sorted(log_df["action"].dropna().astype(str).unique().tolist()) if not log_df.empty and "action" in log_df.columns else [""]
        action_filter = st.selectbox("Action", action_options)
    with c3:
        max_rows = st.number_input("Rows", min_value=50, max_value=500, value=300, step=50)

    if opp_filter and not log_df.empty:
        log_df = log_df[log_df["opportunity_id"].astype(str).str.contains(opp_filter, case=False, na=False)]
    if action_filter and not log_df.empty:
        log_df = log_df[log_df["action"].astype(str).eq(action_filter)]

    if log_df.empty:
        st.info("No logs found.")
    else:
        st.dataframe(log_df.head(int(max_rows)), use_container_width=True, hide_index=True, height=560)
