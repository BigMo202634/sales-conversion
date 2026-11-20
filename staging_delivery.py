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

import ai_engine
import alerts
import businesses as business_config
from webhook_logic import routed_messages, rule_decision


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

CONVERSATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    business_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    customer TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""
HISTORY_TURNS = 12
HISTORY_DAYS = 7

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
                "text": {"preview_url": False, "body": item["reply"]}}
        if item.get("message_id"):
            body["context"] = {"message_id": item["message_id"]}
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


def load_history(db, business_id, channel, customer):
    """The last few turns with this customer, oldest first."""
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT role, body FROM conversation_messages "
            "WHERE business_id = %s AND channel = %s AND customer = %s "
            "AND created_at > now() - make_interval(days => %s) "
            "ORDER BY id DESC LIMIT %s",
            (business_id, channel, customer, HISTORY_DAYS, HISTORY_TURNS))
        rows = cursor.fetchall()
    return [{"role": role, "content": body} for role, body in reversed(rows)]


def save_turns(db, business_id, channel, customer, inbound, outbound):
    with db.cursor() as cursor:
        for role, body in (("user", inbound), ("assistant", outbound)):
            cursor.execute(
                "INSERT INTO conversation_messages (business_id, channel, customer, role, body) "
                "VALUES (%s, %s, %s, %s, %s)", (business_id, channel, customer, role, body))
        cursor.execute("DELETE FROM conversation_messages "
                       "WHERE created_at < now() - make_interval(days => %s)", (HISTORY_DAYS,))
    db.commit()


def ai_reply(message, business, history, env):
    return ai_engine.reply(message, business, history, env)


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
    items = routed_messages(payload, businesses)
    if not items:
        # Status updates, media, or a message to an account no business owns.
        log("no_reply_needed", reason="no_text_message_for_known_business")
        return
    with connect(config["DATABASE_URL"]) as db:
        _update(db, SCHEMA, ())
        _update(db, CONVERSATION_SCHEMA, ())
        for item in items:
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
            item = rule_decision(item, business, env)
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
                if inserted and item["action"] in alerts.REASONS:
                    history = load_history(db, business.id, channel, item["sender"])
                    alerts.notify_owner(business, item, history, item["action"], config, send, env)
                continue
            # The claim above is committed, so a duplicate event never reaches the AI.
            history = load_history(db, business.id, channel, item["sender"])
            ai = ai_reply(item["body"], business, history, env)
            if ai:
                item = {**item, **ai}
                _update(db, "UPDATE message_inbox SET intent = %s, updated_at = now() "
                            "WHERE channel = %s AND message_id = %s", (item["intent"], *key))
                if ai["needs_human"]:
                    log("handoff_requested", business=business.id, channel=channel,
                        intent=item["intent"])
            else:
                log("rule_reply", business=business.id, channel=channel,
                    ai_enabled=ai_engine.enabled(business, env))
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
                save_turns(db, business.id, channel, item["sender"], item["body"], item["reply"])
                _update(db, "UPDATE message_inbox SET state = 'sent', "
                            "outgoing_message_id = %s, updated_at = now() "
                            "WHERE channel = %s AND message_id = %s", (outgoing_id, *key))
            if item.get("needs_human"):
                alerts.notify_owner(business, item, history, "ai_handoff", config, send, env)
