# Test delivery gate

Sending stays off until `SEND_ENABLED=1` (the old `WA_SEND_ENABLED=1` also
works). Without it, signed events are drafted and discarded: nothing is sent
or stored.

The send path in `staging_delivery.py` needs a durable PostgreSQL database.
Render's free web service has an ephemeral filesystem, and a free Render
Postgres database expires after 30 days, so it only suits short testing.

Before a controlled test:

1. Provision PostgreSQL and set its private `DATABASE_URL` in Render. Use a
   paid always-on web service before production traffic.
2. Set `GRAPH_VERSION` to the Meta Graph API version of the test app
   (for example `v23.0`).
3. For each test business, fill in its `channels` IDs and `test_recipients`
   in `businesses.json`, and set the env vars named in its `secrets`:
   a WhatsApp Cloud API token for `whatsapp_token`, and a Page access token
   (Page linked to the Instagram professional account) for `page_token`.
   WhatsApp test recipients are phone numbers in international digits, no
   `+`. Messenger and Instagram test recipients are the page-scoped sender
   IDs Meta shows in the webhook event.
4. Set `SEND_ENABLED=1`.
5. Per channel, test one product question and a repeated copy of the same
   signed event: exactly one reply should be recorded. Test STOP, "human",
   "I have paid" and an unlisted sender: none should get an automatic reply.

A message is skipped (no record, no send) when its sender isn't on that
business's test list or the business has no token for that channel. Missing
`DATABASE_URL` or `GRAPH_VERSION` returns 503 so Meta retries later.

The `message_inbox` table stores channel, inbound message ID, business,
account, sender, intent, state and the outgoing message ID. It does **not**
store message text. A failed or timed-out send becomes `review` and is never
resent automatically, because Meta may have accepted it. `suppressed` rows
(handoff, payment, opt-out) need a person to follow up; there is no operator
inbox or alert yet.

The Meta callback and the API subdomain stay unchanged until end-to-end test
delivery and production readiness are established.
