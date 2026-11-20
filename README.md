# Sales Conversion Agent webhook (staging)

One webhook service for many client businesses, across WhatsApp, Facebook
Messenger and Instagram DMs. It serves `GET /health`, answers Meta's
`GET /webhook` subscription challenge, and checks the `X-Hub-Signature-256`
HMAC on every `POST /webhook`.

**By default it drafts replies and discards them. It sends nothing.** Sending is
gated; see [STAGING_DELIVERY.md](STAGING_DELIVERY.md). When sending is on and an AI
provider is configured, the AI writes the replies (see "AI replies" below).
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

Pick a provider with `AI_PROVIDER`:

| Env var | Meaning |
|---|---|
| `AI_PROVIDER` | `anthropic` (default) or `openai_compatible` |
| `ANTHROPIC_API_KEY` | For `anthropic`: required. Without it, rule replies are used |
| `AI_BASE_URL` | For `openai_compatible`: the server's `/v1` URL |
| `AI_API_KEY` | For `openai_compatible`: the key, if the server needs one |
| `AI_MODEL` | Model name (required for `openai_compatible`; default `claude-opus-5-5` for `anthropic`) |
| `AI_REPLIES` | Set to `0` to switch AI off for every business |

Free test setups with `AI_PROVIDER=openai_compatible`:

- Groq free tier: `AI_BASE_URL=https://api.groq.com/openai/v1`,
  `AI_MODEL=openai/gpt-oss-120b`, `AI_API_KEY` from console.groq.com.
- Gemini free tier: `AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`,
  `AI_MODEL=gemini-2.5-flash`, `AI_API_KEY` from aistudio.google.com.
- Ollama on your own computer: `ollama pull qwen2.5:7b`, expose port 11434
  with a tunnel (for example `cloudflared tunnel --url http://localhost:11434`),
  then `AI_BASE_URL=https://<tunnel-host>/v1`, `AI_MODEL=qwen2.5:7b`. Render
  cannot reach `localhost`, and the computer must stay on.

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
| `secrets` | **Names** of env vars holding `whatsapp_token`, `page_token`, `payment_number`, `payment_name`, `owner_alert_numbers` |

Never put tokens or payment details in this repository; set them in Render's
Environment page under the names listed in `secrets`. A product with no price
is never quoted: the reply says the team will confirm.

## Owner takeover, payments and reminders

**Alerts.** When the AI says a customer is ready to order or needs the team,
or a rule hands the chat over (asks for a person, says they paid, asks for
payment details when none are set up), the customer gets a short
acknowledgement and the owner gets a WhatsApp alert from the business number:
customer number, `wa.me` link and the last few messages. Owner numbers
(international digits, comma-separated) go in the env var named by
`secrets.owner_alert_numbers`, e.g. `OIM_OWNER_ALERT_NUMBERS`.

**Owner mode.** From that moment the assistant stops answering that customer.
Every new customer message is forwarded to the owner instead. The owner
answers by swipe-replying to an alert; the text is sent to the customer from
the business number and kept in the assistant's memory. Replying `done` to an
alert hands the chat back to the assistant. Owner mode also ends by itself
after 24 hours without activity. A message from an owner number that is not a
swipe-reply to an alert is treated as a normal customer message, so the owner
can still test the assistant from the same phone.

**Payments.** If `payment_number` and `payment_name` are set (OIM:
`OIM_MOMO_NUMBER`, `OIM_MOMO_NAME`), the agent sends those exact details when a
buyer asks how to pay. The AI never writes account numbers; it only asks for
them to be attached. "I have paid" opens owner mode and alerts the owner to
verify.

**Reminders.** `GET /tasks/reminders?key=<TASKS_KEY>` re-alerts the owner every
10 minutes (up to 6 times) while a customer is waiting for the owner. Call it
every 5 minutes from a free scheduler such as cron-job.org; that also keeps the
free Render instance awake.

WhatsApp limits: the business number can only send free-form messages to
someone (owner or customer) who wrote to it in the last 24 hours, and in Meta
development mode only to allowed test numbers. Opt-outs never alert. Photos
(e.g. payment screenshots) are not handled yet. Logs show `alert_sent`,
`owner_relayed`, `handoff_closed` and `reminders_checked`, never message text.

## Render Web Service

- Build command: `python -m pip install -r requirements.txt && python -m compileall -q .`
- Start command: `python app.py`
- Health check path: `/health`
- Environment: `WA_VERIFY_TOKEN` (random private value), `META_APP_SECRET`

The service rejects all webhook requests until both values are set. Render
supplies `PORT`. Test with `python -m unittest -v`; the delivery tests also
need `TEST_DATABASE_URL` pointing at an empty scratch PostgreSQL database.

The OIM entry uses the Meta test number's phone number ID
(`1514208075102159`, app "Sales Conversion Agent") so demos reply as OIM.

`sales-conversion-mvp/` is the earlier offline prototype; the webhook no
longer uses it.
