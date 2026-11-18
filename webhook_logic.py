"""Pure staging adapter from signed Meta events to offline sales reply drafts.

This module never calls Meta, an AI provider, or a database. Drafts are
ephemeral and must not be treated as customer responses.
"""

import importlib.util
import os
from pathlib import Path

import oim_catalog


def _load_prototype():
    path = Path(__file__).parent / "sales-conversion-mvp" / "agent.py"
    spec = importlib.util.spec_from_file_location("_offline_sales_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_prototype = _load_prototype()


def text_messages(payload):
    """Extract only inbound text messages; ignore status and media events."""
    if not isinstance(payload, dict):
        return []
    found = []
    entries = payload.get("entry", [])
    if not isinstance(entries, list):
        return []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata", {})
            phone_id = metadata.get("phone_number_id") if isinstance(metadata, dict) else None
            messages = value.get("messages", [])
            if not isinstance(messages, list):
                continue
            for message in messages:
                if not isinstance(message, dict) or message.get("type") != "text":
                    continue
                body = message.get("text", {})
                body = body.get("body") if isinstance(body, dict) else None
                sender, message_id = message.get("from"), message.get("id")
                if not all(isinstance(v, str) and v.strip() for v in (body, sender, message_id)):
                    continue
                if len(body) > 4096:
                    continue
                found.append({"message_id": message_id, "sender": sender,
                              "phone_number_id": phone_id, "body": body})
    return found


def draft_replies(payload, industry="oim-fragrance"):
    """Return safe offline drafts for testing, with no sending or persistence."""
    if industry not in ("oim-fragrance", "perfume-beauty", "fashion"):
        raise ValueError("Unsupported industry")
    drafts = []
    for item in text_messages(payload):
        if industry == "oim-fragrance":
            decision = oim_catalog.reply(
                item["body"],
                momo_number=os.environ.get("OIM_MOMO_NUMBER"),
                momo_name=os.environ.get("OIM_MOMO_NAME"),
            )
        else:
            decision = _prototype.reply(item["body"], industry)
        drafts.append({**item, "intent": decision["intent"],
                       "reply": decision["reply"], "action": decision["action"]})
    return drafts
