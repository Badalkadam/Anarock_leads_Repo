import pandas as pd
import streamlit as st

from config import CACHE_TTL_SECONDS, clean_role


def apply_global_styles():
    st.markdown("""
    <style>
    :root {
        --anarock-red: #b3261e;
        --ink: #17202a;
        --muted: #657080;
        --line: #dfe4ea;
        --surface: #ffffff;
        --canvas: #f6f7f9;
        --teal: #0f766e;
    }

    .stApp {
        background: var(--canvas);
        color: var(--ink);
    }

    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"] {
        display: none;
        height: 0;
    }

    .block-container {
        max-width: 1380px;
        padding-top: 0.35rem;
        padding-bottom: 2rem;
    }

    h1, h2, h3, h4, h5, h6, p, label, span {
        letter-spacing: 0;
    }

    [data-testid="stSidebar"] {
        background: var(--surface);
        border-right: 1px solid var(--line);
    }

    [data-testid="stSidebarContent"],
    [data-testid="stSidebarUserContent"] {
        padding-top: 0.75rem;
    }

    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.75rem;
    }

    .app-header {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 1.5rem;
        border-bottom: 1px solid var(--line);
        padding: 0.15rem 0 1.1rem;
        margin-bottom: 1.25rem;
    }

    .brand-kicker {
        margin: 0 0 0.25rem;
        color: var(--anarock-red);
        font-size: 0.74rem;
        font-weight: 800;
        text-transform: uppercase;
    }

    .app-header h1 {
        margin: 0;
        color: var(--ink);
        font-size: 1.65rem;
        line-height: 1.15;
        font-weight: 800;
    }

    .header-copy {
        margin: 0.5rem 0 0;
        color: var(--muted);
        font-size: 0.98rem;
    }

    .header-chip {
        min-width: 190px;
        background: var(--surface);
        border: 1px solid var(--line);
        border-left: 4px solid var(--teal);
        border-radius: 8px;
        padding: 0.8rem 0.95rem;
        color: var(--ink);
        font-weight: 700;
    }

    .header-chip small {
        display: block;
        margin-top: 0.2rem;
        color: var(--muted);
        font-weight: 500;
    }

    .sidebar-brand {
        border-bottom: 1px solid var(--line);
        padding-bottom: 0.85rem;
        margin-bottom: 0.3rem;
    }

    .sidebar-brand strong {
        display: block;
        color: var(--anarock-red);
        font-size: 1.15rem;
        font-weight: 900;
    }

    .sidebar-brand span {
        color: var(--muted);
        font-size: 0.82rem;
    }

    div[data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-left: 4px solid var(--anarock-red);
        border-radius: 8px;
        padding: 0.85rem 0.95rem;
        min-height: 104px;
        box-shadow: 0 8px 22px rgba(23, 32, 42, 0.04);
    }

    div[data-testid="stMetric"] label {
        color: var(--muted);
        font-weight: 700;
    }

    div[data-testid="stMetricValue"] {
        color: var(--ink);
        font-weight: 850;
    }

    div[data-testid="stVegaLiteChart"] {
        background: var(--surface);
        border-radius: 8px;
    }

    .dashboard-note {
        margin: 0.2rem 0 0.8rem;
        color: var(--muted);
        font-size: 0.88rem;
    }

    .section-rule {
        height: 1px;
        background: var(--line);
        margin: 0.6rem 0 1rem;
    }

    .lead-snapshot {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.95rem 1rem;
        margin: 0.2rem 0 1rem;
    }

    .lead-snapshot strong {
        display: block;
        margin-bottom: 0.25rem;
        color: var(--ink);
    }

    .lead-snapshot span {
        color: var(--muted);
        font-size: 0.92rem;
    }

    .stButton > button,
    .stDownloadButton > button,
    [data-testid="stFormSubmitButton"] button {
        border-radius: 8px;
        font-weight: 750;
        border: 1px solid var(--line);
    }

    .stDataFrame {
        border: 1px solid var(--line);
        border-radius: 8px;
        overflow: hidden;
    }

    @media (max-width: 760px) {
        .app-header {
            display: block;
        }

        .header-chip {
            margin-top: 1rem;
            min-width: 0;
        }
    }
    </style>
    """, unsafe_allow_html=True)


def html_escape(value):
    text = str(value or "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_header(current_user):
    if current_user:
        access_label = f"{current_user.get('name') or current_user.get('email')} | {clean_role(current_user.get('role')).title()}"
    else:
        access_label = "Access pending"

    st.markdown(f"""
    <div class="app-header">
        <div>
            <p class="brand-kicker">ANAROCK Pipeline Console</p>
            <h1>Anarock Collaboration Tracker</h1>
        </div>
        <div class="header-chip">
            {html_escape(access_label)}
            <small>Data cache refreshes every {CACHE_TTL_SECONDS} seconds</small>
        </div>
    </div>
    """, unsafe_allow_html=True)


def page_heading(title, caption=""):
    st.subheader(title)
    if caption:
        st.caption(caption)
    st.markdown('<div class="section-rule"></div>', unsafe_allow_html=True)


def format_cr(value):
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return "0.00"


def date_value(value):
    if value in (None, "") or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()
