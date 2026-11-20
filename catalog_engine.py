"""Rule-based reply drafts for any business, driven by its catalog config.

Guardrails come first: opt-out, human handoff and payment claims never get a
sales reply. Prices come only from the business's configured catalog. Stock,
delivery dates and payment status are never inferred.
"""

import os
import re

INDUSTRY_GREETINGS = {
    "perfume-beauty": "Welcome to {name}! Are you shopping for an everyday scent, a gift, or a special occasion?",
    "fashion": "Welcome to {name}! Are you looking for an outfit, shoes, or a bag today?",
    "hair": "Welcome to {name}! Are you looking for a wig, extensions, or a hair service today?",
    "aesthetics": "Welcome to {name}! Which treatment are you interested in, and when would you like to come in?",
    "general": "Welcome to {name}! What are you looking for today?",
}


def _money(value):
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def _norm(text):
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def _products(business):
    return business.catalog.get("products", [])


def _prices(business, product):
    prices = product.get("prices") or business.catalog.get("default_prices") or {}
    return {str(k): v for k, v in prices.items()}


def _product_in(text, business):
    normalized = _norm(text)
    for product in _products(business):
        for label in [product["name"], *product.get("aliases", [])]:
            if re.search(rf"(?:^|_){re.escape(_norm(label))}(?:_|$)", normalized):
                return product
    return None


def _variant_in(text, variants):
    # Join "30 ml" into "30ml" so it matches a "30ml" variant key.
    compact = re.sub(r"(\d)\s+([a-z])", r"\1\2", text.lower())
    for variant in sorted(variants, key=len, reverse=True):
        key = re.sub(r"\s+", "", variant.lower())
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", compact):
            return variant
    return None


def _price_list(business, prices):
    return ", ".join(f"{v} {business.currency}{_money(p)}" for v, p in prices.items())


def reply(message, business, env=None):
    """Return {"intent", "action", "reply"} for one customer message."""
    env = os.environ if env is None else env
    text = message.strip()
    lowered = text.lower()
    team = f"the {business.name} team"
    cur, note = business.currency, business.price_note

    if re.search(r"\b(stop|unsubscribe|do not message|don't message)\b", lowered):
        return {"intent": "opt_out", "action": "suppress_followups",
                "reply": "Understood. We won't send further follow-up messages."}
    if re.search(r"\b(human|person|owner|manager|representative)\b", lowered):
        return {"intent": "handoff", "action": "human_handoff",
                "reply": f"I'll pass this to {team} for a personal response."}
    if re.search(r"\b(paid|sent payment|transfer sent|receipt|payment proof)\b", lowered):
        return {"intent": "payment", "action": "verify_payment",
                "reply": f"Thank you. {team[0].upper() + team[1:]} will verify the payment before confirming your order."}
    if re.search(r"\b(momo|mobile money|payment details|payment account|account number|account details|bank details|pay to|pay for|how (?:do|can|should) i pay|where (?:do|can|should) i pay|send (?:me )?(?:the |your )?account)\b", lowered):
        number = business.secret("payment_number", env)
        name = business.secret("payment_name", env)
        if number and name:
            return {"intent": "payment_details", "action": "share_payment_details_draft",
                    "reply": f"{business.name} payment details: {number} ({name}). Please confirm the account name before paying. The team will verify payment before confirming your order."}
        return {"intent": "payment_details", "action": "request_payment_details",
                "reply": f"{team[0].upper() + team[1:]} will share the verified payment details before you pay."}
    if re.search(r"\b(deliver|delivery|shipping|ship|dispatch|pickup|pick up)\b", lowered):
        return {"intent": "delivery", "action": "explain_delivery",
                "reply": business.delivery or "Tell us your area and order details so the team can confirm delivery options and timing."}

    product = _product_in(text, business)
    if product:
        prices = _prices(business, product)
        variant = _variant_in(text, prices)
        if variant:
            return {"intent": "price", "action": "quote_price",
                    "reply": f"{product['name']} {variant} is {cur}{_money(prices[variant])}{note}. The team will confirm availability before you order."}
        if prices:
            return {"intent": "product", "action": "ask_variant",
                    "reply": f"{product['name']} comes in these listed options and{note} prices: {_price_list(business, prices)}. Which one would you like? The team will confirm availability."}
        return {"intent": "product", "action": "check_product",
                "reply": f"Thanks for asking about {product['name']}. The team will confirm the current price and availability for you."}

    shared = business.catalog.get("default_prices") or {}
    variant = _variant_in(text, shared)
    if variant:
        return {"intent": "variant", "action": "ask_product",
                "reply": f"Our {variant}{note} price is {cur}{_money(shared[variant])}. Which product would you like?"}

    if re.search(r"\b(price|prices|catalog|catalogue|list|products|how much|sizes|available|stock)\b", lowered):
        names = ", ".join(p["name"] for p in _products(business))
        if not names:
            return {"intent": "catalog", "action": "request_product",
                    "reply": "Which product are you interested in? The team will confirm the current price and availability."}
        prices = f"{note.strip().capitalize() or 'Listed'} options and prices: {_price_list(business, shared)}. " if shared else ""
        return {"intent": "catalog", "action": "show_catalog",
                "reply": f"{business.name}: {names}. {prices}Which one interests you?"}

    greeting = business.greeting or INDUSTRY_GREETINGS[business.industry].format(name=business.name)
    return {"intent": "general", "action": "qualify_need", "reply": greeting}
