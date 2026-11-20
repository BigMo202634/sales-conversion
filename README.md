# Sales Conversion Agent webhook (staging)

One webhook service for many client businesses, across WhatsApp, Facebook
Messenger and Instagram DMs. It serves `GET /health`, answers Meta's
`GET /webhook` subscription challenge, and checks the `X-Hub-Signature-256`
HMAC on every `POST /webhook`.

**By default it drafts replies and discards them. It sends nothing.** Sending is
gated; see [STAGING_DELIVERY.md](STAGING_DELIVERY.md). When sending is on and
`ANTHROPIC_API_KEY` is set, Claude writes the replies (see "AI replies" below).
Do not connect a live business number yet.

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
5. If the message passed those guardrails, `ai_engine.py` asks Claude for a
   salesperson-style reply using only that business's facts and the last few
   turns of the chat. Any AI failure falls back to the rule reply from step 4.

## AI replies

The rule engine always runs first: opt-outs, "talk to a human", payment
claims and payment-detail requests never reach the AI. For everything else
Claude replies like a friendly salesperson: it finds out what the customer
wants, recommends a listed product and size, handles price worries with a
smaller listed option, and asks for quantity and delivery area. It may only use
the products, prices and delivery wording in `businesses.json`; it never
invents stock, discounts, delivery dates or fees, never confirms payment or
orders, and never shares payment details. When the customer is ready to order
or upset, the reply says the team will follow up and the event is logged as
`handoff_requested`.

| Env var | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | Required to turn AI replies on. Without it, rule replies are used |
| `AI_MODEL` | Optional model override (default `claude-opus-5-5`) |
| `AI_REPLIES` | Set to `0` to switch AI off for every business |

A business can also set `"ai": false` to keep rule replies, and
`sales_notes` (free text) to give the AI real selling points, e.g. how long a
scent lasts or which items are bestsellers.

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
| `sales_notes` | Optional true selling points the AI may use |
| `ai` | `false` keeps this business on rule replies |
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
