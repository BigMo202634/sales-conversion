"""Opt-in, test-recipient-only WhatsApp reply delivery with durable deduplication.

No send occurs unless every required production setting is present. A failed or
ambiguous send is held for manual review, never retried automatically.
"""

import json
import os
import re
from urllib import request

from webhook_logic import draft_replies


SCHEMA = """
CREATE TABLE IF NOT EXISTS webhook_inbox (
    message_id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    phone_number_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'suppressed', 'attempted', 'sent', 'review')),
    meta_message_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class ConfigurationError(RuntimeError):
    pass


def settings(env=None):
    env = os.environ if env is None else env
    required = ("DATABASE_URL", "WA_ACCESS_TOKEN", "WA_PHONE_NUMBER_ID",
                "WA_GRAPH_VERSION", "WA_ALLOWED_TEST_RECIPIENTS")
    if any(not env.get(key) for key in required):
        raise ConfigurationError("Missing delivery configuration")
    recipients = {x.strip() for x in env["WA_ALLOWED_TEST_RECIPIENTS"].split(",") if x.strip()}
    if not recipients or any(not re.fullmatch(r"[1-9][0-9]{6,14}", x) for x in recipients):
        raise ConfigurationError("Invalid test-recipient allowlist")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", env["WA_GRAPH_VERSION"]):
        raise ConfigurationError("Invalid Graph API version")
    if not re.fullmatch(r"[0-9]+", env["WA_PHONE_NUMBER_ID"]):
        raise ConfigurationError("Invalid business phone ID")
    return {**{key: env[key] for key in required}, "recipients": recipients}


def send_text(item, config):
    """Return Meta's message ID; network failures are ambiguous to the caller."""
    url = ("https://graph.facebook.com/" + config["WA_GRAPH_VERSION"] + "/" +
           config["WA_PHONE_NUMBER_ID"] + "/messages")
    body = json.dumps({"messaging_product": "whatsapp", "recipient_type": "individual",
                       "to": item["sender"], "type": "text",
                       "context": {"message_id": item["message_id"]},
                       "text": {"preview_url": False, "body": item["reply"]}}).encode()
    req = request.Request(url, body, method="POST", headers={
        "Authorization": "Bearer " + config["WA_ACCESS_TOKEN"],
        "Content-Type": "application/json"})
    with request.urlopen(req, timeout=8) as response:
        result = json.load(response)
    return result["messages"][0]["id"]


def process(payload, config=None, connect=None, send=send_text):
    """Consume a signed event with at-most-one send attempt per inbound ID.

    The claim is committed before the network call. If that call fails or the
    process crashes, the attempted row blocks retries and needs manual review.
    """
    config = settings() if config is None else config
    if connect is None:
        import psycopg
        connect = psycopg.connect
    drafts = draft_replies(payload)
    if not drafts:
        return
    with connect(config["DATABASE_URL"]) as db:
        with db.cursor() as cursor:
            cursor.execute(SCHEMA)
        db.commit()
        for item in drafts:
            sender = item["sender"]
            phone_id = item["phone_number_id"]
            # No record or send for numbers outside the explicit test scope.
            if (sender not in config["recipients"] or
                    phone_id != config["WA_PHONE_NUMBER_ID"]):
                continue
            is_handoff = item["action"] in ("human_handoff", "verify_payment",
                                             "suppress_followups", "request_payment_details")
            initial = "suppressed" if is_handoff else "pending"
            with db.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO webhook_inbox (message_id, sender, phone_number_id, intent, state) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING",
                    (item["message_id"], sender, phone_id, item["intent"], initial))
                inserted = cursor.rowcount == 1
            db.commit()
            if not inserted or is_handoff:
                continue
            # A crash after this commit can lose a reply, but cannot duplicate it.
            with db.cursor() as cursor:
                cursor.execute("UPDATE webhook_inbox SET state = 'attempted', updated_at = now() "
                               "WHERE message_id = %s AND state = 'pending'",
                               (item["message_id"],))
            db.commit()
            try:
                outgoing_id = send(item, config)
            except Exception:
                # No automatic retry: a timeout may mean Meta accepted the send.
                with db.cursor() as cursor:
                    cursor.execute("UPDATE webhook_inbox SET state = 'review', updated_at = now() "
                                   "WHERE message_id = %s", (item["message_id"],))
                db.commit()
            else:
                with db.cursor() as cursor:
                    cursor.execute("UPDATE webhook_inbox SET state = 'sent', "
                                   "meta_message_id = %s, updated_at = now() "
                                   "WHERE message_id = %s",
                                   (outgoing_id, item["message_id"]))
                db.commit()
