"""Per-business configuration: one entry per client business.

Each business has its own catalog, delivery note, greeting, channel account IDs
and test recipients. Secrets are never stored here: a business names the
environment variables that hold its access tokens and payment details.

Load order: the BUSINESSES_JSON environment variable (the whole JSON list),
then the file named by BUSINESSES_FILE, then businesses.json next to this file.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

CHANNELS = ("whatsapp", "instagram", "messenger")
INDUSTRIES = ("perfume-beauty", "fashion", "hair", "aesthetics", "general")
DEFAULT_FILE = Path(__file__).parent / "businesses.json"


class BusinessConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Business:
    id: str
    name: str
    industry: str
    currency: str
    channels: dict
    catalog: dict
    delivery: str = ""
    greeting: str = ""
    price_note: str = ""
    test_recipients: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)

    def secret(self, key, env=None):
        """Return the value of the env var this business names for `key`."""
        env = os.environ if env is None else env
        name = self.secrets.get(key)
        return env.get(name, "") if name else ""


def _parse(entry):
    if not isinstance(entry, dict):
        raise BusinessConfigError("Each business must be an object")
    business_id = entry.get("id", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", business_id):
        raise BusinessConfigError("Business id must be lowercase letters, digits and dashes")
    if entry.get("industry") not in INDUSTRIES:
        raise BusinessConfigError(f"{business_id}: industry must be one of {INDUSTRIES}")
    channels = {k: str(v) for k, v in entry.get("channels", {}).items() if v}
    if set(channels) - set(CHANNELS):
        raise BusinessConfigError(f"{business_id}: unknown channel")
    recipients = {}
    for channel, ids in entry.get("test_recipients", {}).items():
        if channel not in CHANNELS or not isinstance(ids, list):
            raise BusinessConfigError(f"{business_id}: bad test_recipients")
        ids = frozenset(str(x).strip() for x in ids if str(x).strip())
        if any(not re.fullmatch(r"[1-9][0-9]{4,24}", x) for x in ids):
            raise BusinessConfigError(f"{business_id}: test recipients must be digits only")
        recipients[channel] = ids
    catalog = entry.get("catalog", {})
    if not isinstance(catalog, dict) or not isinstance(catalog.get("products", []), list):
        raise BusinessConfigError(f"{business_id}: catalog.products must be a list")
    return Business(
        id=business_id,
        name=str(entry.get("name") or business_id),
        industry=entry["industry"],
        currency=str(entry.get("currency", "")),
        channels=channels,
        catalog=catalog,
        delivery=str(entry.get("delivery", "")),
        greeting=str(entry.get("greeting", "")),
        price_note=str(entry.get("price_note", "")),
        test_recipients=recipients,
        secrets={k: str(v) for k, v in entry.get("secrets", {}).items()},
    )


def parse(entries):
    """Validate a list of business entries and return {id: Business}."""
    if not isinstance(entries, list):
        raise BusinessConfigError("Business config must be a JSON list")
    businesses, accounts = {}, set()
    for entry in entries:
        business = _parse(entry)
        if business.id in businesses:
            raise BusinessConfigError(f"Duplicate business id {business.id}")
        for channel, account in business.channels.items():
            if (channel, account) in accounts:
                raise BusinessConfigError(f"{channel} account {account} is used twice")
            accounts.add((channel, account))
        businesses[business.id] = business
    return businesses


def load(env=None):
    env = os.environ if env is None else env
    if env.get("BUSINESSES_JSON"):
        return parse(json.loads(env["BUSINESSES_JSON"]))
    path = Path(env.get("BUSINESSES_FILE") or DEFAULT_FILE)
    with open(path, encoding="utf-8") as handle:
        return parse(json.load(handle))


def find(businesses, channel, account_id):
    """Return the business that owns this channel account, or None."""
    for business in businesses.values():
        if account_id and business.channels.get(channel) == account_id:
            return business
    return None
