import streamlit as st

from auth import upsert_user
from config import clean_role
from db import invalidate_read_caches, read_df, seed_dropdowns, setup_database
from lead_pages import dropdown_values
from styles import page_heading


def render_setup(current_user, user_email):
    users_df = read_df("users")
    user_count = len(users_df)
    is_admin = current_user and clean_role(current_user.get("role")) == "admin"

    if user_count > 0 and not is_admin:
        page_heading("Access Restricted", "Setup is available only for admin users.")
        st.error("You do not have permission to open Setup.")
        st.stop()

    page_heading("Database Setup", "Bootstrap the app without leaving this screen.")
    if st.button("Create or verify database tables", type="primary", use_container_width=True):
        setup_database()
        seed_dropdowns()
        invalidate_read_caches()
        st.success("Database setup completed.")

    tables = {
        "Leads": "leads",
        "Users": "users",
        "Dropdowns": "dropdowns",
        "Activity Log": "activity_log",
    }
    cols = st.columns(len(tables))
    for idx, (label, table_name) in enumerate(tables.items()):
        try:
            count = len(read_df(table_name))
        except Exception:
            count = 0
        cols[idx].metric(label, f"{count:,}")

    can_manage_users = user_count == 0 or is_admin

    if can_manage_users:
        form_title = "Create first admin user" if user_count == 0 else "Add or update user"
        st.markdown(f"#### {form_title}")
        with st.form("bootstrap_user_form"):
            c1, c2 = st.columns(2)
            with c1:
                new_name = st.text_input("Name", value="Badal Kadam")
                new_email = st.text_input("Email", value=user_email or "1553218@anarock.com")
                new_role = st.selectbox(
                    "Role",
                    ["admin", "manager", "user"],
                    index=0 if user_count == 0 else 2,
                    disabled=user_count == 0,
                )
            with c2:
                new_state = st.selectbox("State", dropdown_values("State") or [""], index=0)
                new_city = st.selectbox("City", dropdown_values("City") or [""], index=0)
                new_manager = st.text_input("Manager", value="")
            create_user = st.form_submit_button("Save User", type="primary", use_container_width=True)

        if create_user:
            if not new_email.strip():
                st.error("Email is required.")
            elif not new_name.strip():
                st.error("Name is required.")
            else:
                role_to_save = "admin" if user_count == 0 else new_role
                upsert_user(new_name, new_email, new_state, new_city, role_to_save, new_manager, "Yes")
                st.success(f"User saved: {new_email.strip().lower()} as {role_to_save}")
                st.info("Refresh Data, then use this email in the sidebar.")
    else:
        st.info("Only an admin can add or update users after the first user has been created.")

    if current_user and clean_role(current_user.get("role")) == "admin":
        sample_email = user_email or "your.email@company.com"
        with st.expander("SQL fallback"):
            st.code(f"""
INSERT INTO users (name, email, state, city, role, active) VALUES
('Badal Kadam', '{sample_email}', 'Maharashtra', 'Mumbai', 'admin', 'Yes')
ON CONFLICT (email) DO UPDATE SET role = 'admin', active = 'Yes';
            """, language="sql")

        st.markdown("#### Active users")
        st.dataframe(users_df, use_container_width=True, hide_index=True, height=360)
