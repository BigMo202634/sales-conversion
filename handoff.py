"""Per-customer "owner mode": while a handoff is open the AI stays quiet.

A handoff opens when a chat needs a person (ready buyer, payment, asks for a
person). Customer messages are then forwarded to the owner instead of being
answered. The owner answers by swipe-replying to an alert on WhatsApp; the
alert's message ID maps back to the customer (alert_links). The owner replies
"done" to an alert to hand the chat back. A handoff with no activity for
HANDOFF_HOURS expires and the AI resumes.
"""

HANDOFF_HOURS = 24
REMINDER_MINUTES = 10
MAX_REMINDERS = 6
DONE_WORDS = {"done", "#done", "ai on", "resume"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoffs (
    business_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    customer TEXT NOT NULL,
    reason TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    customer_waiting_since TIMESTAMPTZ,
    reminded_at TIMESTAMPTZ,
    reminders INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (business_id, channel, customer)
);
CREATE TABLE IF NOT EXISTS alert_links (
    alert_message_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    customer TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _run(db, statement, params=()):
    with db.cursor() as cursor:
        cursor.execute(statement, params)
        rows = cursor.fetchall() if cursor.description else None
    db.commit()
    return rows


def ensure_schema(db):
    _run(db, SCHEMA)


def open_handoff(db, business_id, channel, customer, reason):
    _run(db, "INSERT INTO handoffs (business_id, channel, customer, reason, "
             "customer_waiting_since) VALUES (%s, %s, %s, %s, now()) "
             "ON CONFLICT (business_id, channel, customer) DO UPDATE SET reason = EXCLUDED.reason, "
             "customer_waiting_since = now(), reminded_at = NULL, reminders = 0, updated_at = now()",
         (business_id, channel, customer, reason))


def is_active(db, business_id, channel, customer):
    rows = _run(db, "SELECT 1 FROM handoffs WHERE business_id = %s AND channel = %s "
                    "AND customer = %s AND updated_at > now() - make_interval(hours => %s)",
                (business_id, channel, customer, HANDOFF_HOURS))
    return bool(rows)


def customer_wrote(db, business_id, channel, customer):
    _run(db, "UPDATE handoffs SET customer_waiting_since = COALESCE(customer_waiting_since, now()), "
             "updated_at = now() WHERE business_id = %s AND channel = %s AND customer = %s",
         (business_id, channel, customer))


def owner_replied(db, business_id, channel, customer):
    _run(db, "UPDATE handoffs SET customer_waiting_since = NULL, reminded_at = NULL, "
             "reminders = 0, updated_at = now() "
             "WHERE business_id = %s AND channel = %s AND customer = %s",
         (business_id, channel, customer))


def close(db, business_id, channel, customer):
    _run(db, "DELETE FROM handoffs WHERE business_id = %s AND channel = %s AND customer = %s",
         (business_id, channel, customer))


def link_alert(db, alert_message_id, business_id, channel, customer):
    _run(db, "INSERT INTO alert_links (alert_message_id, business_id, channel, customer) "
             "VALUES (%s, %s, %s, %s) ON CONFLICT (alert_message_id) DO NOTHING",
         (alert_message_id, business_id, channel, customer))
    _run(db, "DELETE FROM alert_links WHERE created_at < now() - make_interval(days => 7)")


def find_link(db, business_id, alert_message_id):
    if not alert_message_id:
        return None
    rows = _run(db, "SELECT channel, customer FROM alert_links "
                    "WHERE business_id = %s AND alert_message_id = %s",
                (business_id, alert_message_id))
    return tuple(rows[0]) if rows else None


def due_reminders(db):
    """Open handoffs where the customer has waited too long for the owner."""
    return [tuple(r) for r in _run(
        db, "SELECT business_id, channel, customer FROM handoffs "
            "WHERE customer_waiting_since IS NOT NULL AND reminders < %s "
            "AND updated_at > now() - make_interval(hours => %s) "
            "AND COALESCE(reminded_at, customer_waiting_since) "
            "    < now() - make_interval(mins => %s)",
        (MAX_REMINDERS, HANDOFF_HOURS, REMINDER_MINUTES))]


def mark_reminded(db, business_id, channel, customer):
    _run(db, "UPDATE handoffs SET reminded_at = now(), reminders = reminders + 1 "
             "WHERE business_id = %s AND channel = %s AND customer = %s",
         (business_id, channel, customer))
