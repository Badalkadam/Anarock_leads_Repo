from datetime import datetime


LEAD_COLUMNS = [
    "opportunity_id", "date_created", "referring_business", "receiving_business",
    "client_business_name", "client_contact_name", "lead_description", "client_category",
    "city", "state", "degree_of_involvement", "date_accepted", "lead_status",
    "reason_for_rejection", "meeting_conducted", "meeting_date", "proposal_submitted",
    "proposal_date", "pipeline_value", "revenue_realised",
    "revenue_booking_date", "status", "remarks", "lead_shared_by", "assigned_to",
    "next_followup_date", "duplicate_flag", "duplicate_reason", "created_by", "updated_by",
    "last_update_date"
]

USER_COLUMNS = ["name", "email", "state", "city", "role", "manager", "active"]
DROPDOWN_COLUMNS = ["type", "value"]
LOG_COLUMNS = ["log_id", "opportunity_id", "changed_by", "changed_on", "action", "field_changed", "old_value", "new_value"]

STATE_CODES = {
    "Maharashtra": "MH", "Karnataka": "KA", "Delhi": "DL", "Tamil Nadu": "TN",
    "Telangana": "TG", "Gujarat": "GJ", "West Bengal": "WB", "Kerala": "KL",
    "Haryana": "HR", "Uttar Pradesh": "UP"
}

DASHBOARD_COLORS = [
    "#b3261e", "#0f766e", "#2563eb", "#d97706", "#475569",
    "#7c3aed", "#0ea5e9", "#16a34a", "#db2777", "#525252"
]

CACHE_TTL_SECONDS = 30
MAX_RETRIES = 3


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize(x):
    return str(x or "").strip().lower()


def is_active_user(value):
    return normalize(value) in {"yes", "y", "true", "1", "active"}


def clean_role(value):
    role = normalize(value or "user")
    if role not in {"user", "manager", "admin"}:
        return "user"
    return role
