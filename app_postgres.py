import streamlit as st

st.set_page_config(page_title="Anarock Collaboration Tracker", layout="wide")

from activity import render_activity
from auth import (
    clear_query_email,
    find_active_user,
    get_query_email,
    remember_query_email,
)
from dashboard import render_dashboard
from db import ensure_database_ready, invalidate_read_caches, read_df
from lead_pages import render_add_lead, render_search, render_update
from setup_page import render_setup
from styles import apply_global_styles, page_heading, render_header


apply_global_styles()
ensure_database_ready()

users_count = len(read_df("users"))
remembered_email = get_query_email()

with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <strong>ANAROCK</strong>
        <span>Collaboration Tracker</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### Access")
    remembered_user = find_active_user(remembered_email) if remembered_email else None
    if remembered_email and not remembered_user:
        clear_query_email()
        remembered_email = ""

    if remembered_user:
        user_email = remembered_email
        current_user = remembered_user
        st.caption(f"Signed in as {user_email}")
    else:
        user_email = st.text_input(
            "Your email",
            value="",
            key="access_email",
            placeholder="name@company.com",
            autocomplete="off",
        )
        current_user = find_active_user(user_email)
        if current_user:
            remember_query_email(user_email)

    if current_user:
        role = current_user["role"]
        manager_state = current_user.get("state", "")
        user_name = current_user.get("name", "") or user_email
        st.success(f"{user_name} | {role.title()}")
        if role == "manager":
            st.caption(f"State access: {manager_state or 'Not configured'}")
        elif role == "admin":
            st.caption("Access: all leads")
        else:
            st.caption("Access: own leads")
    else:
        role = ""
        manager_state = ""
        if users_count == 0:
            st.info("Create the first admin user to start.")
        elif user_email:
            st.warning("This email is not active in Users table.")
        else:
            st.info("Enter your registered email.")

    st.divider()
    if current_user:
        pages = ["Dashboard", "Add Lead", "Search Leads", "Update Lead", "Activity Log"]
        if role == "admin":
            pages.append("Setup")
        page = st.radio("Workspace", pages, label_visibility="collapsed")
    elif users_count == 0:
        page = "Setup"
        st.caption("First-time setup mode")
    else:
        page = "Login"
        st.caption("Workspace unlocks after email verification")

    if st.button("Refresh Data", use_container_width=True):
        invalidate_read_caches()
        st.rerun()

    if current_user and st.button("Logout", use_container_width=True):
        clear_query_email()
        if "access_email" in st.session_state:
            del st.session_state["access_email"]
        st.rerun()

render_header(current_user)

if page == "Login":
    page_heading("Verify Access", "Enter a registered active email to open Anarock Collaboration Tracker.")
    if user_email:
        st.error("This email is not active in the users database.")
    else:
        st.info("Enter your registered email in the sidebar.")
    st.stop()

if page == "Dashboard":
    render_dashboard(user_email, role, manager_state)
elif page == "Add Lead":
    render_add_lead(user_email)
elif page == "Search Leads":
    render_search(user_email, role, manager_state)
elif page == "Update Lead":
    render_update(user_email, role, manager_state)
elif page == "Activity Log":
    render_activity(user_email, role, manager_state)
elif page == "Setup" and (users_count == 0 or role == "admin"):
    render_setup(current_user, user_email)
else:
    page_heading("Access Restricted", "This workspace is available only for admin users.")
    st.error("You do not have permission to open this page.")
