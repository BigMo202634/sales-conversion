"""Shared test fixtures: sample businesses and Meta webhook events."""

import json
from pathlib import Path

import businesses as business_config

WA_PHONE_ID = "123456789"
PAGE_ID = "555000111"
IG_ID = "17841400000000"
CUSTOMER_WA = "233123456789"
CUSTOMER_PSID = "7000000001"
CUSTOMER_IGSID = "8000000001"


def oim_entry(**overrides):
    entries = json.loads((Path(__file__).parent / "businesses.json").read_text(encoding="utf-8"))
    entry = next(e for e in entries if e["id"] == "oim-fragrance")
    entry["channels"] = {"whatsapp": WA_PHONE_ID, "messenger": PAGE_ID, "instagram": IG_ID}
    entry["test_recipients"] = {"whatsapp": [CUSTOMER_WA], "messenger": [CUSTOMER_PSID],
                                "instagram": [CUSTOMER_IGSID]}
    entry.update(overrides)
    return entry


FASHION_ENTRY = {
    "id": "ada-styles",
    "name": "Ada Styles",
    "industry": "fashion",
    "currency": "₦",
    "channels": {"whatsapp": "987654321"},
    "catalog": {"products": [
        {"name": "Ankara Midi Dress", "aliases": ["midi dress", "ankara dress"],
         "prices": {"S": 25000, "M": 25000, "L": 27500}},
        {"name": "Leather Tote", "aliases": ["tote"]},
    ]},
}


def sample_businesses():
    return business_config.parse([oim_entry(), FASHION_ENTRY])


def whatsapp_event(body="How much is it?", sender=CUSTOMER_WA, phone_id=WA_PHONE_ID,
                   message_type="text", message_id="wamid.123", reply_to=None):
    message = {"id": message_id, "from": sender, "type": message_type, "text": {"body": body}}
    if reply_to:
        message["context"] = {"id": reply_to}
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": phone_id}, "messages": [message]}}]}]}


def messaging_event(obj="page", body="How much is it?", sender=CUSTOMER_PSID,
                    account=PAGE_ID, mid="m_123", echo=False):
    message = {"mid": mid, "text": body}
    if echo:
        message["is_echo"] = True
    return {"object": obj, "entry": [{"id": account, "time": 1, "messaging": [{
        "sender": {"id": sender}, "recipient": {"id": account}, "timestamp": 1,
        "message": message}]}]}
