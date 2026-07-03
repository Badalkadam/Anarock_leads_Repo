from datetime import datetime
import hashlib

import pandas as pd
import streamlit as st

from config import CACHE_TTL_SECONDS, STATE_CODES, clean_role, normalize, now_str
from db import append_row, db_execute, invalidate_read_caches, read_df
from styles import date_value, format_cr, html_escape, page_heading


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def dropdown_values(type_name):
    """Get all values for a dropdown type."""
    query = "SELECT DISTINCT value FROM dropdowns WHERE type = %s ORDER BY value;"
    results = db_execute(query, [type_name], fetch_all=True)
    if not results:
        return []
    return [r["value"] for r in results]


def make_state_code(state):
    if not state:
        return "XX"
    if state in STATE_CODES:
        return STATE_CODES[state]
    return "".join([x[0] for x in state.split()])[:2].upper() or "XX"


def generate_opportunity_id(state):
    """Generate next opportunity ID for a state."""
    year = datetime.now().year
    prefix = f"OPP-{make_state_code(state)}-{year}-"

    query = """
        SELECT opportunity_id FROM leads
        WHERE opportunity_id LIKE %s
        ORDER BY opportunity_id DESC LIMIT 1;
    """
    result = db_execute(query, [f"{prefix}%"], fetch_one=True)
    max_no = 0
    if result:
        try:
            max_no = int(result["opportunity_id"].split("-")[-1])
        except Exception:
            pass
    return f"{prefix}{max_no + 1:05d}"


def check_duplicate(client_name, city):
    """Check for duplicate client in same city."""
    new_name = normalize(client_name)
    new_city = normalize(city)

    query = """
        SELECT opportunity_id, client_business_name, city FROM leads
        WHERE LOWER(TRIM(client_business_name)) = %s
           OR (LOWER(TRIM(client_business_name)) = %s AND LOWER(TRIM(city)) = %s)
        LIMIT 1;
    """
    result = db_execute(query, [new_name, new_name, new_city], fetch_one=True)

    if result:
        opp = result["opportunity_id"]
        if normalize(result.get("city", "")) == new_city:
            return "Yes", f"Same client and city already exists: {opp}"
        return "Yes", f"Same client already exists: {opp}"
    return "No", ""


def log_activity(opp, changed_by, action, field="", old_val="", new_val=""):
    """Log an activity."""
    log_id = f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    append_row("activity_log", {
        "log_id": log_id,
        "opportunity_id": opp,
        "changed_by": changed_by,
        "changed_on": now_str(),
        "action": action,
        "field_changed": field,
        "old_value": "" if old_val is None else str(old_val),
        "new_value": "" if new_val is None else str(new_val),
    })


def add_lead(payload):
    """Create a new lead."""
    opp = generate_opportunity_id(payload.get("state", ""))
    dup, reason = check_duplicate(payload.get("client_business_name", ""), payload.get("city", ""))
    ts = now_str()
    created_by = payload.get("created_by", "")

    lead_data = {
        "opportunity_id": opp,
        "date_created": ts,
        "referring_business": payload.get("referring_business", ""),
        "receiving_business": payload.get("receiving_business", ""),
        "client_business_name": payload.get("client_business_name", ""),
        "client_contact_name": payload.get("client_contact_name", ""),
        "lead_description": payload.get("lead_description", ""),
        "client_category": payload.get("client_category", ""),
        "city": payload.get("city", ""),
        "state": payload.get("state", ""),
        "degree_of_involvement": payload.get("degree_of_involvement", ""),
        "lead_status": "New",
        "pipeline_value": payload.get("pipeline_value", 0),
        "remarks": payload.get("remarks", ""),
        "lead_shared_by": payload.get("lead_shared_by", ""),
        "assigned_to": payload.get("assigned_to", ""),
        "duplicate_flag": dup,
        "duplicate_reason": reason,
        "created_by": created_by,
        "updated_by": created_by,
        "last_update_date": ts,
    }
    append_row("leads", lead_data)
    log_activity(opp, created_by, "CREATE", "", "", "Lead created")
    return opp, dup, reason


def visible_leads_query(email, role, manager_state):
    """Build a WHERE clause based on user role and access."""
    role = clean_role(role)
    email = normalize(email)

    if role == "user" and email:
        return "WHERE LOWER(TRIM(lead_shared_by)) = %s", [email]
    elif role == "manager" and manager_state:
        return "WHERE state = %s", [manager_state]
    elif role == "admin":
        return "", []
    else:
        return "WHERE 1=0", []


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def visible_leads(email, role, manager_state):
    """Get leads visible to the current user."""
    where_clause, params = visible_leads_query(email, role, manager_state)
    query = f"SELECT * FROM leads {where_clause} ORDER BY date_created DESC;"
    results = db_execute(query, params, fetch_all=True)
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def filter_leads(df, state="", city="", status="", category=""):
    """Filter a leads dataframe."""
    if df.empty:
        return df
    if state:
        df = df[df["state"] == state]
    if city:
        df = df[df["city"] == city]
    if status:
        df = df[df["lead_status"] == status]
    if category:
        df = df[df["client_category"] == category]
    return df


def update_lead(opp, updates, changed_by):
    """Update a lead and log changes."""
    query = "SELECT * FROM leads WHERE opportunity_id = %s;"
    current = db_execute(query, [opp], fetch_one=True)
    if not current:
        raise ValueError("Opportunity ID not found.")

    update_fields = []
    params = []
    for key, value in updates.items():
        if value is None:
            continue
        if str(current.get(key, "")) == str(value):
            continue
        update_fields.append(f"{key} = %s")
        params.append(value)
        if key not in ["updated_by", "last_update_date"]:
            log_activity(opp, changed_by, "UPDATE", key, current.get(key), value)

    if not update_fields:
        return

    update_fields.append("updated_by = %s")
    update_fields.append("last_update_date = %s")
    params.append(changed_by)
    params.append(now_str())
    params.append(opp)

    query = f"UPDATE leads SET {', '.join(update_fields)} WHERE opportunity_id = %s;"
    db_execute(query, params)
    invalidate_read_caches()


def numeric_series(df, col):
    """Convert a dataframe column to numeric."""
    if df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def display_leads(df):
    columns = [
        "opportunity_id", "client_business_name", "lead_status", "pipeline_value",
        "revenue_realised", "state", "city", "client_category", "lead_shared_by",
        "assigned_to", "date_created", "last_update_date"
    ]
    labels = {
        "opportunity_id": "Opportunity ID",
        "client_business_name": "Client",
        "lead_status": "Status",
        "pipeline_value": "Pipeline Rs. Cr",
        "revenue_realised": "Revenue Rs. Cr",
        "state": "State",
        "city": "City",
        "client_category": "Category",
        "lead_shared_by": "Shared By",
        "assigned_to": "Assigned To",
        "date_created": "Created",
        "last_update_date": "Last Update",
    }
    if df.empty:
        return df
    existing = [col for col in columns if col in df.columns]
    view = df[existing].copy()
    return view.rename(columns=labels)


def filter_controls(prefix):
    states = dropdown_values("State")
    cities = dropdown_values("City")
    statuses = dropdown_values("Lead Status")
    categories = dropdown_values("Client Category")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        state = st.selectbox("State", [""] + states, key=f"{prefix}_state")
    with c2:
        city = st.selectbox("City", [""] + cities, key=f"{prefix}_city")
    with c3:
        status = st.selectbox("Lead Status", [""] + statuses, key=f"{prefix}_status")
    with c4:
        category = st.selectbox("Client Category", [""] + categories, key=f"{prefix}_category")
    return state, city, status, category


def search_dataframe(df, search_text):
    if df.empty or not search_text:
        return df
    needle = normalize(search_text)
    search_cols = [
        "opportunity_id", "client_business_name", "client_contact_name",
        "city", "state", "lead_status", "assigned_to", "lead_shared_by"
    ]
    mask = pd.Series(False, index=df.index)
    for col in search_cols:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.lower().str.contains(needle, na=False, regex=False)
    return df[mask]


def render_add_lead(user_email):
    page_heading("Create Lead", "Capture a lead with the minimum fields needed for fast routing.")
    states = dropdown_values("State") or [""]
    cities = dropdown_values("City") or [""]
    categories = dropdown_values("Client Category") or ["Other"]

    with st.form("add_lead_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### Client")
            client_business_name = st.text_input("Client Business Name *")
            client_contact_name = st.text_input("Client Contact Name")
            client_category = st.selectbox("Client Category", categories)
            lead_description = st.text_area("Lead Description", height=110)
        with c2:
            st.markdown("#### Market")
            state = st.selectbox("State", states)
            city = st.selectbox("City", cities)
            pipeline_value = st.number_input("Pipeline Value (Rs. Cr)", min_value=0.0, step=0.1)
            involvement = st.selectbox("Source Involvement", ["Low", "Medium", "High"], index=1)
        with c3:
            st.markdown("#### Ownership")
            referring_business = st.text_input("Referring Business", value="CLA")
            receiving_business = st.text_input("Receiving Business", value="Office Leasing")
            lead_shared_by = st.text_input("Lead Shared By", value=user_email, placeholder="person@anarock.com",
                                           help="Enter the email ID of the person who shared this lead.")
            assigned_to = st.text_input("Assigned To")
            remarks = st.text_area("Remarks", height=110)

        submitted = st.form_submit_button("Create Lead", type="primary", use_container_width=True)

    if submitted:
        if not client_business_name.strip():
            st.error("Client Business Name is required.")
            return

        lead_payload = {
            "referring_business": referring_business,
            "receiving_business": receiving_business,
            "client_business_name": client_business_name,
            "client_contact_name": client_contact_name,
            "lead_description": lead_description,
            "client_category": client_category,
            "city": city,
            "state": state,
            "degree_of_involvement": involvement,
            "pipeline_value": pipeline_value,
            "remarks": remarks,
            "lead_shared_by": lead_shared_by,
            "assigned_to": assigned_to,
            "created_by": user_email,
        }

        with st.spinner("Saving lead..."):
            opp, dup, reason = add_lead(lead_payload)
        st.success(f"Lead created: {opp}")
        if dup == "Yes":
            st.warning(reason)


def render_search(user_email, role, manager_state):
    page_heading("Lead Search", "Filter, inspect, and export visible opportunities.")
    df = visible_leads(user_email, role, manager_state)
    f_state, f_city, f_status, f_category = filter_controls("search")
    search_text = st.text_input("Search client, opportunity, city, owner, or assignee")

    filtered = filter_leads(df, f_state, f_city, f_status, f_category)
    filtered = search_dataframe(filtered, search_text)

    k1, k2, k3 = st.columns(3)
    k1.metric("Rows", f"{len(filtered):,}")
    k2.metric("Pipeline Rs. Cr", format_cr(numeric_series(filtered, "pipeline_value").sum()))
    k3.metric("Revenue Rs. Cr", format_cr(numeric_series(filtered, "revenue_realised").sum()))

    st.dataframe(display_leads(filtered), use_container_width=True, hide_index=True, height=560)
    if not filtered.empty:
        st.download_button(
            "Download filtered CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            "anarock_leads_filtered.csv",
            "text/csv",
            use_container_width=True,
        )


def render_update(user_email, role, manager_state):
    page_heading("Update Lead", "Change status, ownership, revenue, and follow-up details.")
    df = visible_leads(user_email, role, manager_state)
    if df.empty:
        st.info("No leads available for this access scope.")
        return

    opps = df["opportunity_id"].dropna().astype(str).tolist()
    label_map = {
        row["opportunity_id"]: f"{row['opportunity_id']} | {row.get('client_business_name', '')} | {row.get('lead_status', '')}"
        for _, row in df.fillna("").iterrows()
    }
    selected_opp = st.selectbox("Select Opportunity", opps, format_func=lambda opp: label_map.get(opp, opp))
    selected = df[df["opportunity_id"] == selected_opp].iloc[0].to_dict()

    st.markdown(f"""
    <div class="lead-snapshot">
        <strong>{html_escape(selected.get('client_business_name', ''))}</strong>
        <span>{html_escape(selected_opp)} | {html_escape(selected.get('city', ''))}, {html_escape(selected.get('state', ''))} | Current status: {html_escape(selected.get('lead_status', ''))}</span>
    </div>
    """, unsafe_allow_html=True)

    status_options = dropdown_values("Lead Status") or ["New"]
    current_status = str(selected.get("lead_status") or "New")
    status_index = status_options.index(current_status) if current_status in status_options else 0

    with st.form("update_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            lead_status = st.selectbox("Lead Status", status_options, index=status_index)
            date_accepted = st.date_input("Date Accepted", value=date_value(selected.get("date_accepted")))
            reason_rejection = st.text_area("Reason for Rejection", value=str(selected.get("reason_for_rejection") or ""), height=96)
        with c2:
            meeting_conducted = st.selectbox(
                "Meeting Conducted",
                ["", "Yes", "No"],
                index=["", "Yes", "No"].index(str(selected.get("meeting_conducted") or "")) if str(selected.get("meeting_conducted") or "") in ["", "Yes", "No"] else 0,
            )
            meeting_date = st.date_input("Meeting Date", value=date_value(selected.get("meeting_date")))
            proposal_submitted = st.selectbox(
                "Proposal Submitted",
                ["", "Yes", "No"],
                index=["", "Yes", "No"].index(str(selected.get("proposal_submitted") or "")) if str(selected.get("proposal_submitted") or "") in ["", "Yes", "No"] else 0,
            )
        with c3:
            proposal_date = st.date_input("Proposal Date", value=date_value(selected.get("proposal_date")))
            current_revenue = pd.to_numeric(selected.get("revenue_realised", 0), errors="coerce")
            revenue_realised = st.number_input(
                "Revenue Realised (Rs. Cr)",
                min_value=0.0,
                value=float(0 if pd.isna(current_revenue) else current_revenue),
                step=0.1,
            )
            revenue_booking_date = st.date_input("Revenue Booking Date", value=date_value(selected.get("revenue_booking_date")))

        c4, c5, c6 = st.columns(3)
        with c4:
            status_text = st.text_input("Status Note", value=str(selected.get("status") or ""))
        with c5:
            assigned_to = st.text_input("Assigned To", value=str(selected.get("assigned_to") or ""))
        with c6:
            next_follow_up = st.date_input("Next Follow-up Date", value=date_value(selected.get("next_followup_date")))
        remarks = st.text_area("Remarks", value=str(selected.get("remarks") or ""), height=110)
        submit_update = st.form_submit_button("Save Update", type="primary", use_container_width=True)

    if submit_update:
        updates = {
            "date_accepted": str(date_accepted) if date_accepted else None,
            "lead_status": lead_status,
            "reason_for_rejection": reason_rejection,
            "meeting_conducted": meeting_conducted,
            "meeting_date": str(meeting_date) if meeting_date else None,
            "proposal_submitted": proposal_submitted,
            "proposal_date": str(proposal_date) if proposal_date else None,
            "revenue_realised": revenue_realised,
            "revenue_booking_date": str(revenue_booking_date) if revenue_booking_date else None,
            "status": status_text,
            "remarks": remarks,
            "assigned_to": assigned_to,
            "next_followup_date": str(next_follow_up) if next_follow_up else None,
        }
        with st.spinner("Saving update..."):
            try:
                update_lead(selected_opp, updates, user_email)
                st.success(f"Updated {selected_opp}")
            except ValueError as exc:
                st.error(str(exc))
