import importlib
import os

import pandas as pd
import psycopg2
import streamlit as st
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

from config import CACHE_TTL_SECONDS, MAX_RETRIES


def get_db_url():
    """Build database URL from Streamlit secrets or environment variables."""
    try:
        db_url = st.secrets["database"].get("url", "").strip()
    except Exception:
        db_url = os.getenv("DATABASE_URL", "").strip()

    if db_url:
        return db_url

    try:
        user = st.secrets["database"]["user"]
        password = st.secrets["database"]["password"]
        host = st.secrets["database"]["host"]
        port = st.secrets["database"]["port"]
        dbname = st.secrets["database"]["name"]
    except Exception:
        user = os.getenv("DB_USER", "")
        password = os.getenv("DB_PASSWORD", "")
        host = os.getenv("DB_HOST", "")
        port = os.getenv("DB_PORT", "5432")
        dbname = os.getenv("DB_NAME", "")

    if not all([user, password, host, dbname]):
        st.error("Database configuration missing. Check Streamlit secrets or environment variables.")
        st.stop()

    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


@st.cache_resource(ttl=3600)
def get_db_pool():
    """Create a connection pool to the database (cached for the session)."""
    db_url = get_db_url()
    try:
        pool = SimpleConnectionPool(1, 5, db_url, sslmode="require")
        return pool
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        st.stop()


def rollback_if_open(conn):
    """Rollback only when psycopg2 still has an open connection."""
    if not conn or getattr(conn, "closed", 1) != 0:
        return
    try:
        conn.rollback()
    except psycopg2.Error:
        pass


def release_connection(pool, conn):
    """Return open connections to the pool and discard closed ones."""
    if not conn:
        return
    try:
        pool.putconn(conn, close=(getattr(conn, "closed", 1) != 0))
    except psycopg2.Error:
        pass


def db_execute(query, params=None, fetch_one=False, fetch_all=False):
    """
    Execute a query with automatic retry on transient failures.
    """
    pool = get_db_pool()
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, params or ())

        if fetch_one:
            result = cursor.fetchone()
            conn.commit()
            return result
        elif fetch_all:
            result = cursor.fetchall()
            conn.commit()
            return result
        else:
            conn.commit()
            return True
    except Exception as e:
        rollback_if_open(conn)
        st.error(f"Database error: {e}")
        st.stop()
    finally:
        release_connection(pool, conn)


def db_execute_many(query, params_list):
    """Execute multiple queries (for batch inserts)."""
    pool = get_db_pool()
    conn = None
    try:
        conn = pool.getconn()
        cursor = conn.cursor()
        for params in params_list:
            cursor.execute(query, params)
        conn.commit()
        return True
    except Exception as e:
        rollback_if_open(conn)
        st.error(f"Database batch error: {e}")
        st.stop()
    finally:
        release_connection(pool, conn)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def read_table(table_name):
    """Cached read of an entire table."""
    query = f"SELECT * FROM {table_name} ORDER BY created_at DESC NULLS LAST;"
    rows = db_execute(query, fetch_all=True)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def read_df(table_name):
    """Wrapper around read_table for compatibility."""
    return read_table(table_name)


def invalidate_read_caches():
    """Clear cached database-backed reads across modules."""
    if hasattr(read_table, "clear"):
        read_table.clear()

    for module_name, fn_name in (
        ("lead_pages", "dropdown_values"),
        ("lead_pages", "visible_leads"),
        ("activity", "read_activity_log"),
    ):
        try:
            module = importlib.import_module(module_name)
            cached_fn = getattr(module, fn_name, None)
            if cached_fn and hasattr(cached_fn, "clear"):
                cached_fn.clear()
        except Exception:
            pass


def append_row(table_name, data_dict):
    """Append a single row to a table."""
    columns = list(data_dict.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    col_names = ", ".join(columns)
    values = [data_dict[c] for c in columns]

    query = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders});"
    db_execute(query, values)
    invalidate_read_caches()


def append_rows(table_name, data_list):
    """Append multiple rows to a table."""
    if not data_list:
        return
    columns = list(data_list[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    col_names = ", ".join(columns)
    values_list = [[row.get(c, None) for c in columns] for row in data_list]

    query = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders});"
    db_execute_many(query, values_list)
    invalidate_read_caches()


def setup_database():
    """Create tables if they don't exist."""
    db_execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            opportunity_id VARCHAR(50) UNIQUE NOT NULL,
            date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            referring_business VARCHAR(255),
            receiving_business VARCHAR(255),
            client_business_name VARCHAR(255) NOT NULL,
            client_contact_name VARCHAR(255),
            lead_description TEXT,
            client_category VARCHAR(100),
            city VARCHAR(100),
            state VARCHAR(100),
            degree_of_involvement VARCHAR(50),
            date_accepted TIMESTAMP,
            lead_status VARCHAR(50) DEFAULT 'New',
            reason_for_rejection TEXT,
            meeting_conducted VARCHAR(10),
            meeting_date TIMESTAMP,
            proposal_submitted VARCHAR(10),
            proposal_date TIMESTAMP,
            pipeline_value NUMERIC(12, 2) DEFAULT 0,
            revenue_realised NUMERIC(12, 2) DEFAULT 0,
            revenue_booking_date TIMESTAMP,
            status VARCHAR(100),
            remarks TEXT,
            lead_shared_by VARCHAR(255),
            assigned_to VARCHAR(255),
            next_followup_date TIMESTAMP,
            duplicate_flag VARCHAR(10),
            duplicate_reason TEXT,
            created_by VARCHAR(255),
            updated_by VARCHAR(255),
            last_update_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_leads_state ON leads(state);
        CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city);
        CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(lead_status);
        CREATE INDEX IF NOT EXISTS idx_leads_opp_id ON leads(opportunity_id);
        CREATE INDEX IF NOT EXISTS idx_leads_shared_by ON leads(lead_shared_by);
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255),
            email VARCHAR(255) UNIQUE NOT NULL,
            state VARCHAR(100),
            city VARCHAR(100),
            role VARCHAR(50) DEFAULT 'user',
            manager VARCHAR(255),
            active VARCHAR(10) DEFAULT 'Yes',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_active ON users(active);
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS dropdowns (
            id SERIAL PRIMARY KEY,
            type VARCHAR(100) NOT NULL,
            value VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(type, value)
        );
        CREATE INDEX IF NOT EXISTS idx_dropdowns_type ON dropdowns(type);
    """)

    db_execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id SERIAL PRIMARY KEY,
            log_id VARCHAR(100) UNIQUE,
            opportunity_id VARCHAR(50),
            changed_by VARCHAR(255),
            changed_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action VARCHAR(50),
            field_changed VARCHAR(100),
            old_value TEXT,
            new_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_log_opp_id ON activity_log(opportunity_id);
        CREATE INDEX IF NOT EXISTS idx_log_changed_by ON activity_log(changed_by);
    """)


def seed_dropdowns():
    """Seed dropdown values if table is empty."""
    df = read_df("dropdowns")
    if len(df) > 0:
        return

    rows = [
        {"type": "Lead Status", "value": "New"},
        {"type": "Lead Status", "value": "Accepted"},
        {"type": "Lead Status", "value": "Rejected"},
        {"type": "Lead Status", "value": "Meeting Done"},
        {"type": "Lead Status", "value": "Proposal Submitted"},
        {"type": "Lead Status", "value": "Won"},
        {"type": "Lead Status", "value": "Lost"},
        {"type": "Client Category", "value": "GCC / Captive Centre"},
        {"type": "Client Category", "value": "Office Leasing & Expansion"},
        {"type": "Client Category", "value": "Lease Expiry / Renewal"},
        {"type": "Client Category", "value": "Startup Funding Series B+"},
        {"type": "Client Category", "value": "Educational Institute Entry"},
        {"type": "Client Category", "value": "Hospital Expansion / Takeover"},
        {"type": "Client Category", "value": "Trade Delegation / Foreign Entry"},
        {"type": "Client Category", "value": "Other"},
        {"type": "State", "value": "Maharashtra"},
        {"type": "State", "value": "Karnataka"},
        {"type": "State", "value": "Delhi"},
        {"type": "State", "value": "Tamil Nadu"},
        {"type": "State", "value": "Telangana"},
        {"type": "State", "value": "Gujarat"},
        {"type": "State", "value": "West Bengal"},
        {"type": "State", "value": "Kerala"},
        {"type": "State", "value": "Haryana"},
        {"type": "State", "value": "Uttar Pradesh"},
        {"type": "City", "value": "Mumbai"},
        {"type": "City", "value": "Pune"},
        {"type": "City", "value": "Bengaluru"},
        {"type": "City", "value": "Delhi"},
        {"type": "City", "value": "Chennai"},
        {"type": "City", "value": "Hyderabad"},
        {"type": "City", "value": "Ahmedabad"},
        {"type": "City", "value": "Kolkata"},
        {"type": "City", "value": "Kochi"},
        {"type": "City", "value": "Gurugram"},
        {"type": "City", "value": "Noida"},
    ]
    append_rows("dropdowns", rows)


@st.cache_resource(show_spinner=False)
def ensure_database_ready():
    setup_database()
    seed_dropdowns()
    return True
