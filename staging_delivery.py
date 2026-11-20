"""Opt-in, test-recipient-only reply delivery with durable deduplication.

Works per business and per channel (WhatsApp, Messenger, Instagram). Nothing is
sent unless SEND_ENABLED=1, the global settings are present, the business has a
token for that channel, and the sender is on that business's test list. A failed
or ambiguous send is held for manual review, never retried automatically.
"""

import json
import os
import re
import sys
from urllib import error, request

import businesses as business_config
from webhook_logic import draft_replies


SCHEMA = """
CREATE TABLE IF NOT EXISTS message_inbox (
    channel TEXT NOT NULL CHECK (channel IN ('whatsapp', 'messenger', 'instagram')),
    message_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    intent TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'suppressed', 'attempted', 'sent', 'review')),
    outgoing_message_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (channel, message_id)
)
"""

HANDOFF_ACTIONS = ("human_handoff", "verify_payment", "suppress_followups",
                   "request_payment_details")
TOKEN_KEYS = {"whatsapp": "whatsapp_token", "messenger": "page_token",
              "instagram": "page_token"}


class ConfigurationError(RuntimeError):
    pass


def log(event, **fields):
    """Write one JSON line to Render's log. Never pass message text or sender IDs."""
    print(json.dumps({"event": event, **fields}), file=sys.stderr, flush=True)


def meta_error(exc):
    """Summarise a failed Meta call without customer data."""
    if isinstance(exc, error.HTTPError):
        try:
            detail = json.load(exc).get("error", {})
        except Exception:
            detail = {}
        return {"http_status": exc.code, "code": detail.get("code"),
                "subcode": detail.get("error_subcode"), "type": detail.get("type"),
                "message": str(detail.get("message", ""))[:200]}
    return {"error": type(exc).__name__}


def send_enabled(env=None):
    env = os.environ if env is None else env
    return "1" in (env.get("SEND_ENABLED"), env.get("WA_SEND_ENABLED"))


def settings(env=None):
    env = os.environ if env is None else env
    version = env.get("GRAPH_VERSION") or env.get("WA_GRAPH_VERSION") or ""
    if not env.get("DATABASE_URL") or not version:
        raise ConfigurationError("Missing delivery configuration")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
        raise ConfigurationError("Invalid Graph API version")
    return {"DATABASE_URL": env["DATABASE_URL"], "GRAPH_VERSION": version}


def send_message(item, token, config):
    """Send one reply and return Meta's message ID.

    Network failures are ambiguous to the caller: Meta may have accepted it.
    """
    base = "https://graph.facebook.com/" + config["GRAPH_VERSION"]
    if item["channel"] == "whatsapp":
        url = base + "/" + item["account_id"] + "/messages"
        body = {"messaging_product": "whatsapp", "recipient_type": "individual",
                "to": item["sender"], "type": "text",
                "context": {"message_id": item["message_id"]},
                "text": {"preview_url": False, "body": item["reply"]}}
    else:
        # Messenger and Instagram (via a linked Facebook Page) use the Send API.
        url = base + "/me/messages"
        body = {"recipient": {"id": item["sender"]}, "messaging_type": "RESPONSE",
                "message": {"text": item["reply"]}}
    req = request.Request(url, json.dumps(body).encode(), method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with request.urlopen(req, timeout=8) as response:
        result = json.load(response)
    if item["channel"] == "whatsapp":
        return result["messages"][0]["id"]
    return result["message_id"]


def _update(db, statement, params):
    with db.cursor() as cursor:
        cursor.execute(statement, params)
        rowcount = cursor.rowcount
    db.commit()
    return rowcount


def process(payload, config=None, businesses=None, connect=None, send=send_message, env=None):
    """Consume a signed event with at most one send attempt per inbound message.

    The claim is committed before the network call. If that call fails or the
    process crashes, the attempted row blocks retries and needs manual review.
    """
    env = os.environ if env is None else env
    config = settings(env) if config is None else config
    businesses = business_config.load(env) if businesses is None else businesses
    if connect is None:
        import psycopg
        connect = psycopg.connect
    drafts = draft_replies(payload, businesses, env)
    if not drafts:
        return
    with connect(config["DATABASE_URL"]) as db:
        _update(db, SCHEMA, ())
        for item in drafts:
            business = businesses[item["business_id"]]
            channel = item["channel"]
            # No record or send outside this business's explicit test scope.
            if item["sender"] not in business.recipients(channel, env):
                log("skipped", reason="sender_not_test_recipient", business=business.id,
                    channel=channel)
                continue
            token = business.secret(TOKEN_KEYS[channel], env)
            if not token:
                log("skipped", reason="no_token", business=business.id, channel=channel)
                continue
            key = (channel, item["message_id"])
            is_handoff = item["action"] in HANDOFF_ACTIONS
            inserted = _update(
                db,
                "INSERT INTO message_inbox (channel, message_id, business_id, account_id, "
                "sender, intent, state) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (channel, message_id) DO NOTHING",
                (*key, business.id, item["account_id"], item["sender"], item["intent"],
                 "suppressed" if is_handoff else "pending")) == 1
            if not inserted or is_handoff:
                log("not_sent", reason="duplicate" if not inserted else "handoff",
                    business=business.id, channel=channel, intent=item["intent"])
                continue
            # A crash after this commit can lose a reply, but cannot duplicate it.
            _update(db, "UPDATE message_inbox SET state = 'attempted', updated_at = now() "
                        "WHERE channel = %s AND message_id = %s AND state = 'pending'", key)
            try:
                outgoing_id = send(item, token, config)
            except Exception as exc:
                # No automatic retry: a timeout may mean Meta accepted the send.
                _update(db, "UPDATE message_inbox SET state = 'review', updated_at = now() "
                            "WHERE channel = %s AND message_id = %s", key)
                log("send_failed", business=business.id, channel=channel, **meta_error(exc))
            else:
                log("sent", business=business.id, channel=channel, intent=item["intent"])
                _update(db, "UPDATE message_inbox SET state = 'sent', "
                            "outgoing_message_id = %s, updated_at = now() "
                            "WHERE channel = %s AND message_id = %s", (outgoing_id, *key))
