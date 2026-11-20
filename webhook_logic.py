"""Turn signed Meta events into per-business reply drafts.

Handles WhatsApp Cloud API, Messenger and Instagram messaging events. Each
message is routed to the business that owns the receiving account; messages to
unknown accounts are ignored. This module never calls Meta or a database.
"""

import businesses as business_config
import catalog_engine

MAX_TEXT = 4096
OBJECT_CHANNELS = {
    "whatsapp_business_account": "whatsapp",
    "page": "messenger",
    "instagram": "instagram",
}


def _valid(*values):
    return all(isinstance(v, str) and v.strip() for v in values)


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _whatsapp(entry):
    found = []
    for change in _list(entry.get("changes")):
        value = _dict(_dict(change).get("value"))
        account = _dict(value.get("metadata")).get("phone_number_id")
        for message in _list(value.get("messages")):
            message = _dict(message)
            if message.get("type") != "text":
                continue
            found.append((account, message.get("from"), message.get("id"),
                          _dict(message.get("text")).get("body"),
                          _dict(message.get("context")).get("id")))
    return found


def _messaging(entry):
    """Messenger and Instagram share the Messenger Platform event shape."""
    found = []
    account = entry.get("id")
    for event in _list(entry.get("messaging")):
        event = _dict(event)
        message = _dict(event.get("message"))
        if not message or message.get("is_echo"):
            continue  # Skip our own outgoing messages echoed back.
        found.append((account, _dict(event.get("sender")).get("id"),
                      message.get("mid"), message.get("text"), None))
    return found


def inbound_messages(payload):
    """Extract inbound text messages; ignore statuses, echoes and media."""
    if not isinstance(payload, dict):
        return []
    channel = OBJECT_CHANNELS.get(payload.get("object"))
    if channel is None:
        return []
    extract = _whatsapp if channel == "whatsapp" else _messaging
    found = []
    for entry in _list(payload.get("entry")):
        if not isinstance(entry, dict):
            continue
        for account, sender, message_id, body, reply_to in extract(entry):
            account = str(account) if isinstance(account, (str, int)) else None
            if not _valid(account, sender, message_id, body) or len(body) > MAX_TEXT:
                continue
            found.append({"channel": channel, "account_id": account,
                          "sender": sender, "message_id": message_id, "body": body,
                          "reply_to": reply_to if isinstance(reply_to, str) else None})
    return found


def routed_messages(payload, businesses):
    """Inbound text messages paired with the business that owns the account."""
    routed = []
    for item in inbound_messages(payload):
        business = business_config.find(businesses, item["channel"], item["account_id"])
        if business is not None:
            routed.append({**item, "business_id": business.id})
    return routed


def rule_decision(item, business, env=None):
    decision = catalog_engine.reply(item["body"], business, env)
    return {**item, "intent": decision["intent"], "reply": decision["reply"],
            "action": decision["action"]}


def draft_replies(payload, businesses=None, env=None):
    """Return rule-based drafts for messages to known businesses. Nothing is sent."""
    businesses = business_config.load() if businesses is None else businesses
    return [rule_decision(item, businesses[item["business_id"]], env)
            for item in routed_messages(payload, businesses)]
