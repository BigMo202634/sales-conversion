# Sales Conversion Agent webhook (staging)

One webhook service for many client businesses, across WhatsApp, Facebook
Messenger and Instagram DMs. It serves `GET /health`, answers Meta's
`GET /webhook` subscription challenge, and checks the `X-Hub-Signature-256`
HMAC on every `POST /webhook`.

**By default it drafts replies and discards them. It sends nothing.** Sending is
gated; see [STAGING_DELIVERY.md](STAGING_DELIVERY.md). Replies are still
rule-based, not AI. Do not connect a live business number yet.

## How a message flows

1. Meta posts a signed event. `object` tells us the channel:
   `whatsapp_business_account`, `page` (Messenger) or `instagram`.
2. `webhook_logic.py` pulls out inbound text messages (ignoring statuses,
   echoes of our own replies, and media).
3. Each message is routed to the business that owns the receiving account:
   the WhatsApp phone number ID, the Facebook Page ID or the Instagram account
   ID listed under that business's `channels`. Unknown accounts are ignored.
4. `catalog_engine.py` drafts a reply from that business's own catalog,
   currency, delivery note and greeting. Opt-outs, "talk to a human" and
   payment claims are never answered with a sales reply.

## Adding a business

Add an entry to `businesses.json` (or put the whole list in the
`BUSINESSES_JSON` environment variable, or point `BUSINESSES_FILE` at a file):

| Field | Meaning |
|---|---|
| `id` | Lowercase slug, e.g. `ada-styles` |
| `industry` | `perfume-beauty`, `fashion`, `hair`, `aesthetics` or `general` |
| `currency` | Shown before prices, e.g. `₦` or `GH₵` |
| `channels` | `whatsapp` phone number ID, `messenger` Page ID, `instagram` account ID. Leave empty to ignore that channel |
| `catalog.products` | `name`, optional `aliases`, optional `prices` per option (`{"M": 25000}`) |
| `catalog.default_prices` | Prices shared by every product, e.g. perfume sizes |
| `delivery`, `greeting`, `price_note` | Optional business wording |
| `test_recipients` | Per channel, the only senders who may get real replies while testing |
| `secrets` | **Names** of env vars holding `whatsapp_token`, `page_token`, `payment_number`, `payment_name` |

Never put tokens or payment details in this repository; set them in Render's
Environment page under the names listed in `secrets`. A product with no price
is never quoted: the reply says the team will confirm.

## Render Web Service

- Build command: `python -m pip install -r requirements.txt && python -m compileall -q .`
- Start command: `python app.py`
- Health check path: `/health`
- Environment: `WA_VERIFY_TOKEN` (random private value), `META_APP_SECRET`

The service rejects all webhook requests until both values are set. Render
supplies `PORT`. Test with `python -m unittest -v`.

The OIM entry uses the Meta test number's phone number ID
(`1514208075102159`, app "Sales Conversion Agent") so demos reply as OIM.

`sales-conversion-mvp/` is the earlier offline prototype; the webhook no
longer uses it.
