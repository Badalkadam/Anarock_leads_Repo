import streamlit as st

from config import clean_role, is_active_user, normalize
from db import db_execute, invalidate_read_caches


def get_query_email():
    try:
        value = st.query_params.get("user", "")
    except Exception:
        value = ""
    return normalize(value)


def remember_query_email(email):
    email = normalize(email)
    if not email:
        return
    try:
        st.query_params["user"] = email
    except Exception:
        pass


def clear_query_email():
    try:
        if "user" in st.query_params:
            del st.query_params["user"]
    except Exception:
        pass


def find_active_user(email):
    """Find active user by email."""
    email = normalize(email)
    if not email:
        return None

    query = """
        SELECT * FROM users
        WHERE LOWER(TRIM(email)) = %s
        LIMIT 1;
    """
    result = db_execute(query, [email], fetch_one=True)
    if not result:
        return None
    if not is_active_user(result.get("active")):
        return None
    result = dict(result)
    result["role"] = clean_role(result.get("role"))
    result["email"] = normalize(result.get("email"))
    return result


def upsert_user(name, email, state, city, role="user", manager="", active="Yes"):
    """Add or update a user."""
    query = """
        INSERT INTO users (name, email, state, city, role, manager, active)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (email) DO UPDATE SET
            name = EXCLUDED.name,
            state = EXCLUDED.state,
            city = EXCLUDED.city,
            role = EXCLUDED.role,
            manager = EXCLUDED.manager,
            active = EXCLUDED.active;
    """
    db_execute(query, [
        name.strip(),
        normalize(email),
        state.strip(),
        city.strip(),
        clean_role(role),
        manager.strip(),
        active.strip(),
    ])
    invalidate_read_caches()
