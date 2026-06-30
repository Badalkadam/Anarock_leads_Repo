import os
import ssl
from pathlib import Path

import certifi
import gspread
import pandas as pd
import requests
import streamlit as st
from datetime import datetime
from google.auth.exceptions import TransportError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Lead Management App", layout="wide")

LEADS_SHEET = "Leads_Master"
USERS_SHEET = "Users_Master"
DROPDOWN_SHEET = "Dropdown_Master"
LOG_SHEET = "Activity_Log"

LEAD_COLUMNS = [
    "Opportunity ID","Date Created","Referring Business","Receiving Business",
    "Client Business Name","Client Contact Name","Lead Description","Client Category",
    "City","State","Degree of Source's Involvement","Date Accepted","Lead Status",
    "Reason for Rejection","Meeting Conducted","Meeting Date","Proposal Submitted",
    "Proposal Date","Pipeline Value (Rs. Cr)","Revenue Realised (Rs. Cr)",
    "Revenue Booking Date","Status","Remarks","Lead Shared by","Assigned To",
    "Next Follow-up Date","Duplicate Flag","Duplicate Reason","Created By","Updated By",
    "Last Update Date"
]
USER_COLUMNS = ["Name","Email","State","City","Role","Manager","Active"]
DROPDOWN_COLUMNS = ["Type","Value"]
LOG_COLUMNS = ["Log ID","Opportunity ID","Changed By","Changed On","Action","Field Changed","Old Value","New Value"]

STATE_CODES = {
    "Maharashtra":"MH","Karnataka":"KA","Delhi":"DL","Tamil Nadu":"TN",
    "Telangana":"TG","Gujarat":"GJ","West Bengal":"WB","Kerala":"KL",
    "Haryana":"HR","Uttar Pradesh":"UP"
}

def _windows_ca_pems():
    if not hasattr(ssl, "enum_certificates"):
        return []
    pems = []
    for store_name in ("ROOT", "CA"):
        try:
            certs = ssl.enum_certificates(store_name)
        except Exception:
            continue
        for cert_bytes, encoding, _trust in certs:
            if encoding == "x509_asn":
                try:
                    pems.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
                except Exception:
                    pass
    return list(dict.fromkeys(pems))

def build_ca_bundle():
    certifi_path = Path(certifi.where())
    if os.name != "nt":
        return str(certifi_path)

    try:
        bundle_path = Path(__file__).resolve().parent / ".streamlit" / "combined-ca-bundle.pem"
        windows_pems = _windows_ca_pems()
        if not windows_pems:
            return str(certifi_path)
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_text = certifi_path.read_text(encoding="ascii") + "\n" + "\n".join(windows_pems)
        bundle_path.write_text(bundle_text, encoding="ascii")
        return str(bundle_path)
    except Exception:
        return str(certifi_path)

CA_BUNDLE = build_ca_bundle()
os.environ["REQUESTS_CA_BUNDLE"] = CA_BUNDLE
os.environ["SSL_CERT_FILE"] = CA_BUNDLE

def make_authorized_session(creds):
    refresh_session = requests.Session()
    refresh_session.verify = CA_BUNDLE
    session = AuthorizedSession(creds, auth_request=Request(refresh_session))
    session.verify = CA_BUNDLE
    return session

def stop_for_google_error(exc):
    details = str(exc)
    if isinstance(exc, TransportError) or "CERTIFICATE_VERIFY_FAILED" in details:
        st.error("Google Sheets connection failed because Python could not verify the SSL certificate.")
        st.info(
            "The app now uses a combined certificate bundle for Windows. "
            "Restart Streamlit, then run `pip install -r requirements.txt` if this message remains."
        )
        st.caption(f"Certificate bundle: {CA_BUNDLE}")
    elif isinstance(exc, gspread.exceptions.SpreadsheetNotFound):
        st.error("Google Sheet not found. Check the spreadsheet_id secret and share the Sheet with the service account email.")
    elif isinstance(exc, gspread.exceptions.APIError):
        st.error("Google Sheets API returned an error. Check that Sheets API and Drive API are enabled for the service account project.")
        st.code(details)
    else:
        st.error("Could not connect to Google Sheets.")
        st.code(details)
    st.stop()

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize(x):
    return " ".join(str(x or "").strip().lower().split())

def is_active_user(value):
    return normalize(value) in {"yes", "y", "true", "1", "active"}

def clean_role(value):
    role = normalize(value or "user")
    if role not in {"user", "manager", "admin"}:
        return "user"
    return role

@st.cache_resource(ttl=600)
def google_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    if "gcp_service_account" not in st.secrets:
        st.error("Missing Streamlit secret: [gcp_service_account]")
        st.stop()
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(None, session=make_authorized_session(creds))

def spreadsheet_id():
    try:
        sid = st.secrets["app"]["spreadsheet_id"]
    except Exception:
        sid = ""
    if not sid:
        st.error("Missing Streamlit secret: [app] spreadsheet_id")
        st.stop()
    return sid

@st.cache_resource(ttl=600)
def spreadsheet():
    return google_client().open_by_key(spreadsheet_id())

def get_or_create_ws(name, headers):
    try:
        ss = spreadsheet()
        try:
            ws = ss.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = ss.add_worksheet(title=name, rows=2000, cols=max(len(headers), 10))
        if not ws.row_values(1):
            ws.update("A1", [headers])
            try:
                ws.freeze(rows=1)
            except Exception:
                pass
        return ws
    except Exception as exc:
        stop_for_google_error(exc)

def read_df(name, headers):
    ws = get_or_create_ws(name, headers)
    try:
        rows = ws.get_all_records()
    except Exception as exc:
        stop_for_google_error(exc)
    if not rows:
        return pd.DataFrame(columns=headers)
    df = pd.DataFrame(rows)
    for c in headers:
        if c not in df.columns:
            df[c] = ""
    return df[headers]

def append_row(name, row, headers):
    ws = get_or_create_ws(name, headers)
    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception as exc:
        stop_for_google_error(exc)

def seed_dropdowns():
    df = read_df(DROPDOWN_SHEET, DROPDOWN_COLUMNS)
    if len(df) > 0:
        return
    rows = [
        ["Lead Status","New"],["Lead Status","Accepted"],["Lead Status","Rejected"],
        ["Lead Status","Meeting Done"],["Lead Status","Proposal Submitted"],
        ["Lead Status","Won"],["Lead Status","Lost"],
        ["Client Category","GCC / Captive Centre"],
        ["Client Category","Office Leasing & Expansion"],
        ["Client Category","Lease Expiry / Renewal"],
        ["Client Category","Startup Funding Series B+"],
        ["Client Category","Educational Institute Entry"],
        ["Client Category","Hospital Expansion / Takeover"],
        ["Client Category","Trade Delegation / Foreign Entry"],
        ["Client Category","Other"],
        ["Meeting Conducted","Yes"],["Meeting Conducted","No"],
        ["Proposal Submitted","Yes"],["Proposal Submitted","No"],
        ["State","Maharashtra"],["State","Karnataka"],["State","Delhi"],
        ["State","Tamil Nadu"],["State","Telangana"],["State","Gujarat"],
        ["State","West Bengal"],["State","Kerala"],["State","Haryana"],
        ["State","Uttar Pradesh"],
        ["City","Mumbai"],["City","Pune"],["City","Bengaluru"],["City","Hyderabad"],
        ["City","Chennai"],["City","Delhi"],["City","Noida"],["City","Gurugram"],
        ["City","Ahmedabad"],["City","Kolkata"],["City","Kochi"],
        ["City","Coimbatore"],["City","Indore"],["City","Jaipur"],
        ["City","Thiruvananthapuram"]
    ]
    for r in rows:
        append_row(DROPDOWN_SHEET, r, DROPDOWN_COLUMNS)

def setup_sheets():
    get_or_create_ws(LEADS_SHEET, LEAD_COLUMNS)
    get_or_create_ws(USERS_SHEET, USER_COLUMNS)
    get_or_create_ws(DROPDOWN_SHEET, DROPDOWN_COLUMNS)
    get_or_create_ws(LOG_SHEET, LOG_COLUMNS)
    seed_dropdowns()

def find_active_user(email):
    email = normalize(email)
    if not email:
        return None
    df = read_df(USERS_SHEET, USER_COLUMNS)
    if df.empty:
        return None
    matches = df[df["Email"].astype(str).apply(normalize).eq(email)]
    if matches.empty:
        return None
    for _, row in matches.iterrows():
        if is_active_user(row.get("Active", "")):
            user = {c: str(row.get(c, "")).strip() for c in USER_COLUMNS}
            user["Role"] = clean_role(user.get("Role", "user"))
            return user
    return None

def dropdown_values(t):
    df = read_df(DROPDOWN_SHEET, DROPDOWN_COLUMNS)
    if df.empty:
        return []
    vals = df[df["Type"].astype(str).eq(t)]["Value"].dropna().astype(str).str.strip().tolist()
    return list(dict.fromkeys([v for v in vals if v]))

def make_state_code(state):
    if not state:
        return "XX"
    if state in STATE_CODES:
        return STATE_CODES[state]
    return "".join([x[0] for x in state.split()])[:2].upper() or "XX"

def generate_opportunity_id(state):
    df = read_df(LEADS_SHEET, LEAD_COLUMNS)
    year = datetime.now().year
    prefix = f"OPP-{make_state_code(state)}-{year}-"
    max_no = 0
    if not df.empty:
        for opp in df["Opportunity ID"].astype(str).tolist():
            if opp.startswith(prefix):
                try:
                    max_no = max(max_no, int(opp.split("-")[-1]))
                except Exception:
                    pass
    return f"{prefix}{max_no + 1:05d}"

def check_duplicate(client_name, city):
    df = read_df(LEADS_SHEET, LEAD_COLUMNS)
    if df.empty:
        return "No", ""
    new_name = normalize(client_name)
    new_city = normalize(city)
    for _, r in df.iterrows():
        old_name = normalize(r.get("Client Business Name", ""))
        old_city = normalize(r.get("City", ""))
        old_opp = r.get("Opportunity ID", "")
        if old_name and old_name == new_name:
            if new_city and old_city == new_city:
                return "Yes", f"Same client and city already exists: {old_opp}"
            return "Yes", f"Same client already exists: {old_opp}"
    return "No", ""

def log_activity(opp, changed_by, action, field="", old="", new=""):
    append_row(LOG_SHEET, [
        f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", opp, changed_by,
        now_str(), action, field, "" if old is None else str(old), "" if new is None else str(new)
    ], LOG_COLUMNS)

def add_lead(payload):
    opp = generate_opportunity_id(payload.get("State", ""))
    dup, reason = check_duplicate(payload.get("Client Business Name", ""), payload.get("City", ""))
    ts = now_str()
    created_by = payload.get("Created By", "")
    row = [
        opp, ts,
        payload.get("Referring Business", ""), payload.get("Receiving Business", ""),
        payload.get("Client Business Name", ""), payload.get("Client Contact Name", ""),
        payload.get("Lead Description", ""), payload.get("Client Category", ""),
        payload.get("City", ""), payload.get("State", ""),
        payload.get("Degree of Source's Involvement", ""), "",
        "New", "", "", "", "", "",
        payload.get("Pipeline Value (Rs. Cr)", 0), 0, "", "",
        payload.get("Remarks", ""), payload.get("Lead Shared by", ""),
        payload.get("Assigned To", ""), "", dup, reason,
        created_by, created_by, ts
    ]
    append_row(LEADS_SHEET, row, LEAD_COLUMNS)
    log_activity(opp, created_by, "CREATE", "", "", "Lead created")
    return opp, dup, reason

def visible_leads(email, role, manager_state):
    df = read_df(LEADS_SHEET, LEAD_COLUMNS)
    if df.empty:
        return df
    role = clean_role(role)
    email = normalize(email)
    if role == "user" and email:
        df = df[df["Lead Shared by"].astype(str).str.lower().str.strip().eq(email)]
    elif role == "manager":
        if not manager_state:
            return df.iloc[0:0]
        df = df[df["State"].astype(str).eq(manager_state)]
    elif role != "admin":
        return df.iloc[0:0]
    return df

def filter_leads(df, state="", city="", status="", category=""):
    if df.empty:
        return df
    if state:
        df = df[df["State"].astype(str).eq(state)]
    if city:
        df = df[df["City"].astype(str).eq(city)]
    if status:
        df = df[df["Lead Status"].astype(str).eq(status)]
    if category:
        df = df[df["Client Category"].astype(str).eq(category)]
    return df

def update_lead(opp, updates, changed_by):
    ws = get_or_create_ws(LEADS_SHEET, LEAD_COLUMNS)
    try:
        values = ws.get_all_values()
    except Exception as exc:
        stop_for_google_error(exc)
    if len(values) <= 1:
        raise ValueError("No leads found.")
    headers = values[0]
    col_map = {h: i + 1 for i, h in enumerate(headers)}
    target_row = None
    for n, row in enumerate(values[1:], start=2):
        if row and row[0] == opp:
            target_row = n
            break
    if not target_row:
        raise ValueError("Opportunity ID not found.")
    old_row = values[target_row - 1]
    old = {h: old_row[i] if i < len(old_row) else "" for i, h in enumerate(headers)}
    for field, new in updates.items():
        if field not in col_map:
            continue
        if new is None:
            continue
        if str(old.get(field, "")) != str(new):
            try:
                ws.update_cell(target_row, col_map[field], new)
            except Exception as exc:
                stop_for_google_error(exc)
            if field not in ["Updated By", "Last Update Date"]:
                log_activity(opp, changed_by, "UPDATE", field, old.get(field, ""), new)
    try:
        ws.update_cell(target_row, col_map["Updated By"], changed_by)
        ws.update_cell(target_row, col_map["Last Update Date"], now_str())
    except Exception as exc:
        stop_for_google_error(exc)

def numeric_series(df, col):
    if df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)

# ================= UI =================

st.title("Lead Management App")
st.caption("Free Python version: Streamlit + Google Sheets backend")

with st.sidebar:
    st.header("Access")
    default_email = ""
    try:
        default_email = st.secrets["app"].get("default_user_email", "")
    except Exception:
        pass
    user_email = st.text_input("Your email", value=default_email)
    current_user = find_active_user(user_email)
    if current_user:
        role = current_user["Role"]
        manager_state = current_user.get("State", "")
        user_name = current_user.get("Name", "") or user_email
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
        if user_email:
            st.warning("This email is not active in Users_Master.")
        else:
            st.info("Enter your registered email.")
    st.caption("Roles are controlled from Users_Master.")

tabs = st.tabs(["Setup", "Add Lead", "Search Leads", "Update Lead", "Dashboard", "Activity Log"])

with tabs[0]:
    st.subheader("Setup")
    st.write("Run this once after adding Google Sheet ID and service account credentials.")
    if st.button("Create required Google Sheet tabs"):
        setup_sheets()
        st.success("Setup completed. Tabs created in Google Sheet.")
    st.code("\n".join([LEADS_SHEET, USERS_SHEET, DROPDOWN_SHEET, LOG_SHEET]))
    st.markdown("#### User access format")
    st.dataframe(pd.DataFrame([{
        "Name": "Naveen",
        "Email": "1553218@anarock.com",
        "State": "Maharashtra",
        "City": "Mumbai",
        "Role": "admin",
        "Manager": "",
        "Active": "Yes",
    }]), use_container_width=True, hide_index=True)

if not current_user:
    st.stop()

with tabs[1]:
    st.subheader("Add New Lead")
    states = dropdown_values("State") or [""]
    cities = dropdown_values("City") or [""]
    categories = dropdown_values("Client Category") or ["Other"]
    with st.form("add_lead_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            referring_business = st.text_input("Referring Business", value="CLA")
            receiving_business = st.text_input("Receiving Business", value="Office Leasing")
            client_business_name = st.text_input("Client Business Name *")
            client_contact_name = st.text_input("Client Contact Name")
        with c2:
            client_category = st.selectbox("Client Category", categories)
            city = st.selectbox("City", cities)
            state = st.selectbox("State", states)
            pipeline_value = st.number_input("Pipeline Value (Rs. Cr)", min_value=0.0, step=0.1)
        with c3:
            involvement = st.selectbox("Degree of Source's Involvement", ["Low", "Medium", "High"])
            lead_shared_by = st.text_input("Lead Shared by", value=user_email, disabled=True)
            assigned_to = st.text_input("Assigned To")
            remarks = st.text_area("Remarks")
        lead_description = st.text_area("Lead Description")
        submitted = st.form_submit_button("Create Lead")
    if submitted:
        if not client_business_name.strip():
            st.error("Client Business Name is required.")
        else:
            opp, dup, reason = add_lead({
                "Referring Business": referring_business,
                "Receiving Business": receiving_business,
                "Client Business Name": client_business_name,
                "Client Contact Name": client_contact_name,
                "Lead Description": lead_description,
                "Client Category": client_category,
                "City": city,
                "State": state,
                "Degree of Source's Involvement": involvement,
                "Pipeline Value (Rs. Cr)": pipeline_value,
                "Remarks": remarks,
                "Lead Shared by": lead_shared_by,
                "Assigned To": assigned_to,
                "Created By": user_email,
            })
            st.success(f"Lead created: {opp}")
            if dup == "Yes":
                st.warning(reason)

with tabs[2]:
    st.subheader("Search Leads")
    df = visible_leads(user_email, role, manager_state)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        f_state = st.selectbox("State", [""] + dropdown_values("State"), key="s_state")
    with c2:
        f_city = st.selectbox("City", [""] + dropdown_values("City"), key="s_city")
    with c3:
        f_status = st.selectbox("Lead Status", [""] + dropdown_values("Lead Status"), key="s_status")
    with c4:
        f_category = st.selectbox("Client Category", [""] + dropdown_values("Client Category"), key="s_cat")
    df2 = filter_leads(df, f_state, f_city, f_status, f_category)
    st.write(f"Rows: {len(df2)}")
    st.dataframe(df2, use_container_width=True, hide_index=True)
    st.download_button("Download filtered CSV", df2.to_csv(index=False).encode("utf-8"), "filtered_leads.csv", "text/csv")

with tabs[3]:
    st.subheader("Update Existing Lead")
    df = visible_leads(user_email, role, manager_state)
    if df.empty:
        st.info("No leads available.")
    else:
        opps = df["Opportunity ID"].dropna().astype(str).tolist()
        selected_opp = st.selectbox("Select Opportunity ID", opps)
        selected = df[df["Opportunity ID"] == selected_opp].iloc[0].to_dict()
        st.info(f"Selected: {selected.get('Client Business Name','')} | {selected.get('City','')} | Current status: {selected.get('Lead Status','')}")
        with st.form("update_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                lead_status = st.selectbox("Lead Status", dropdown_values("Lead Status") or ["New"])
                date_accepted = st.date_input("Date Accepted", value=None)
                reason_rejection = st.text_area("Reason for Rejection")
            with c2:
                meeting_conducted = st.selectbox("Meeting Conducted", ["", "Yes", "No"])
                meeting_date = st.date_input("Meeting Date", value=None)
                proposal_submitted = st.selectbox("Proposal Submitted", ["", "Yes", "No"])
            with c3:
                proposal_date = st.date_input("Proposal Date", value=None)
                revenue_realised = st.number_input("Revenue Realised (Rs. Cr)", min_value=0.0, step=0.1)
                revenue_booking_date = st.date_input("Revenue Booking Date", value=None)
            c4, c5, c6 = st.columns(3)
            with c4:
                status_text = st.text_input("Status")
            with c5:
                assigned_to = st.text_input("Assigned To", value=str(selected.get("Assigned To","")))
            with c6:
                next_follow_up = st.date_input("Next Follow-up Date", value=None)
            remarks = st.text_area("Remarks", value=str(selected.get("Remarks","")))
            submit_update = st.form_submit_button("Update Lead")
        if submit_update:
            updates = {
                "Date Accepted": str(date_accepted) if date_accepted else "",
                "Lead Status": lead_status,
                "Reason for Rejection": reason_rejection,
                "Meeting Conducted": meeting_conducted,
                "Meeting Date": str(meeting_date) if meeting_date else "",
                "Proposal Submitted": proposal_submitted,
                "Proposal Date": str(proposal_date) if proposal_date else "",
                "Revenue Realised (Rs. Cr)": revenue_realised,
                "Revenue Booking Date": str(revenue_booking_date) if revenue_booking_date else "",
                "Status": status_text,
                "Remarks": remarks,
                "Assigned To": assigned_to,
                "Next Follow-up Date": str(next_follow_up) if next_follow_up else "",
            }
            update_lead(selected_opp, updates, user_email)
            st.success(f"Updated {selected_opp}")

with tabs[4]:
    st.subheader("Dashboard")
    df = visible_leads(user_email, role, manager_state)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        d_state = st.selectbox("State", [""] + dropdown_values("State"), key="d_state")
    with c2:
        d_city = st.selectbox("City", [""] + dropdown_values("City"), key="d_city")
    with c3:
        d_status = st.selectbox("Lead Status", [""] + dropdown_values("Lead Status"), key="d_status")
    with c4:
        d_category = st.selectbox("Client Category", [""] + dropdown_values("Client Category"), key="d_cat")
    dfd = filter_leads(df, d_state, d_city, d_status, d_category)
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Leads", len(dfd))
    k2.metric("Pipeline Value (Rs. Cr)", round(float(numeric_series(dfd, "Pipeline Value (Rs. Cr)").sum()), 2))
    k3.metric("Revenue Realised (Rs. Cr)", round(float(numeric_series(dfd, "Revenue Realised (Rs. Cr)").sum()), 2))
    if dfd.empty:
        st.info("No data found.")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Leads by Status")
            st.bar_chart(dfd["Lead Status"].replace("", "Blank").value_counts())
            st.markdown("#### Leads by State")
            st.bar_chart(dfd["State"].replace("", "Blank").value_counts())
        with right:
            st.markdown("#### Leads by Person")
            st.bar_chart(dfd["Lead Shared by"].replace("", "Blank").value_counts())
            st.markdown("#### Leads by Category")
            st.bar_chart(dfd["Client Category"].replace("", "Blank").value_counts())

with tabs[5]:
    st.subheader("Activity Log")
    opp_filter = st.text_input("Filter Opportunity ID")
    log_df = read_df(LOG_SHEET, LOG_COLUMNS)
    if role != "admin":
        visible_df = visible_leads(user_email, role, manager_state)
        visible_opps = set(visible_df["Opportunity ID"].dropna().astype(str).tolist())
        log_df = log_df[log_df["Opportunity ID"].astype(str).isin(visible_opps)]
    if opp_filter:
        log_df = log_df[log_df["Opportunity ID"].astype(str).eq(opp_filter)]
    if log_df.empty:
        st.info("No logs found.")
    else:
        st.dataframe(log_df.tail(300).iloc[::-1], use_container_width=True, hide_index=True)
