"""Verified OIM Fragrance facts and conservative staging reply drafts.

No stock, delivery date, or payment status is inferred from these facts.
"""

import re

PRODUCTS = (
    "OIM_BOSS",
    "OIM_BILLONAIRE",
    "OIM_ALPHA",
    "OIM_SEDUCTION",
    "OIM_MIRAYA",
)
SIZE_PRICES_GHS = {3: 15, 6: 25, 12: 60, 30: 120}
FREE_DELIVERY_THRESHOLD_GHS = 200


def _product_in(text):
    normalized = re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")
    for product in PRODUCTS:
        name = product.removeprefix("OIM_")
        if re.search(rf"(?:^|_)(?:OIM_)?{re.escape(name)}(?:_|$)", normalized):
            return product
    return None


def _size_in(text):
    match = re.search(r"\b(3|6|12|30)\s*ml\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _prices():
    return ", ".join(f"{size}ml GH₵{price}" for size, price in SIZE_PRICES_GHS.items())


def reply(message, momo_number=None, momo_name=None):
    """Return a draft decision. Caller must enforce durable opt-out and handoff."""
    text = message.strip()
    lowered = text.lower()
    if re.search(r"\b(stop|unsubscribe|do not message|don't message)\b", lowered):
        return {"intent": "opt_out", "action": "suppress_followups",
                "reply": "Understood. We won't send further follow-up messages."}
    if re.search(r"\b(human|person|owner|manager|representative)\b", lowered):
        return {"intent": "handoff", "action": "human_handoff",
                "reply": "I'll pass this to the OIM team for a personal response."}
    if re.search(r"\b(paid|sent payment|transfer sent|receipt|payment proof)\b", lowered):
        return {"intent": "payment", "action": "verify_payment",
                "reply": "Thank you. The OIM team will verify the payment before confirming your order."}
    if re.search(r"\b(momo|mobile money|payment details|pay to|pay for)\b", lowered):
        if momo_number and momo_name:
            return {"intent": "payment_details", "action": "share_payment_details_draft",
                    "reply": f"OIM MoMo: {momo_number} ({momo_name}). Please confirm the account name in your MoMo app before paying. The team will verify payment before confirming your order."}
        return {"intent": "payment_details", "action": "request_payment_details",
                "reply": "The OIM team will share the verified MoMo details before you pay."}
    if re.search(r"\b(deliver|delivery|shipping|kumasi|outside kumasi)\b", lowered):
        return {"intent": "delivery", "action": "explain_delivery",
                "reply": "Delivery is free within Kumasi for orders of GH₵200 or more. Tell us your area and order details so the team can confirm delivery options and timing."}

    product, size = _product_in(text), _size_in(text)
    if product and size:
        return {"intent": "price", "action": "quote_retail_price",
                "reply": f"{product} {size}ml is GH₵{SIZE_PRICES_GHS[size]} retail. The team will confirm availability before you order."}
    if product:
        return {"intent": "product", "action": "ask_size",
                "reply": f"{product} comes in these listed sizes and retail prices: {_prices()}. Which size would you like? The team will confirm availability."}
    if size:
        return {"intent": "size", "action": "ask_product",
                "reply": f"Our {size}ml retail price is GH₵{SIZE_PRICES_GHS[size]}. Which OIM fragrance would you like?"}
    if re.search(r"\b(price|prices|catalog|list|fragrance|perfume|products|how much|sizes)\b", lowered):
        return {"intent": "catalog", "action": "show_catalog",
                "reply": f"OIM Fragrance: {', '.join(PRODUCTS)}. Retail sizes and prices: {_prices()}. Which fragrance and size interest you?"}
    return {"intent": "general", "action": "qualify_need",
            "reply": "Welcome to OIM Fragrance! Are you shopping for yourself, a gift, or a special occasion? I can share the listed retail sizes and prices."}
