"""WhatsApp alerts to the business owner when a chat needs a person.

Sent when the AI says the customer is ready to order or needs the team, or when
a rule hands the chat over (asks for a person, says they paid, asks for payment
details). Alerts go out from the business's own WhatsApp number to the numbers
in the env var named by secrets["owner_alert_numbers"] (comma-separated digits).

WhatsApp only delivers a free-form message to someone who wrote to that number
in the last 24 hours, so each owner should message the business number once a
day (or we add an approved template later). An alert failure never blocks the
customer's reply.
"""

import json
import re
import sys

REASONS = {
    "ai_handoff": "Customer is ready to order or needs you",
    "human_handoff": "Customer asked to speak to a person",
    "verify_payment": "Customer says they have paid. Please verify",
    "request_payment_details": "Customer asked for payment details",
}
FOLLOW_UPS = {
    "customer_message": "💬 Customer replied",
    "reminder": "⏰ Customer is still waiting for your reply",
}
HOW_TO_REPLY = ("↩️ Swipe-reply to this message to answer the customer. "
                "Reply done to hand the chat back to the assistant.")
MAX_BODY = 1500


def _log(event, **fields):
    print(json.dumps({"event": event, **fields}), file=sys.stderr, flush=True)


def owner_numbers(business, env):
    raw = business.secret("owner_alert_numbers", env)
    return [x.strip() for x in raw.split(",") if re.fullmatch(r"[1-9][0-9]{4,24}", x.strip())]


def _clip(text, limit=200):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def alert_text(business, item, history, reason):
    title = FOLLOW_UPS.get(reason) or "🔔 " + REASONS.get(reason, "Customer needs you")
    lines = [f"{business.name}: {title}"]
    if item["channel"] == "whatsapp":
        lines.append(f"Customer: +{item['sender']} (wa.me/{item['sender']})")
    else:
        lines.append(f"Customer: {item['channel'].capitalize()} chat (reply in your inbox there)")
    if history:
        lines.append("")
        lines.append("Recent chat:")
        for turn in history[-4:]:
            who = "Customer" if turn["role"] == "user" else "Us"
            lines.append(f"{who}: {_clip(turn['content'], 160)}")
    if item.get("body"):
        lines.append("")
        lines.append(f"Customer: {_clip(item['body'])}")
        if item.get("reply"):
            lines.append(f"Us: {_clip(item['reply'])}")
    lines.append("")
    lines.append(HOW_TO_REPLY)
    text = "\n".join(lines)
    return text if len(text) <= MAX_BODY else text[:MAX_BODY - 1] + "…"


def notify_owner(business, item, history, reason, config, send, env):
    """Send one alert per owner number. Returns the sent alert message IDs."""
    numbers = owner_numbers(business, env)
    account = business.channels.get("whatsapp")
    token = business.secret("whatsapp_token", env)
    if not numbers or not account or not token:
        _log("alert_skipped", business=business.id, reason="no_owner_number_or_whatsapp")
        return []
    text = alert_text(business, item, history, reason)
    sent = []
    for number in numbers:
        alert = {"channel": "whatsapp", "account_id": account, "sender": number,
                 "message_id": None, "reply": text}
        try:
            sent.append(send(alert, token, config))
        except Exception as exc:
            _log("alert_failed", business=business.id, error=type(exc).__name__)
    _log("alert_sent", business=business.id, reason=reason, count=len(sent))
    return sent
