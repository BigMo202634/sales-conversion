# OIM test delivery gate

The current Render service stays in draft-only mode. `WA_SEND_ENABLED` is not
set, so signed events are acknowledged without sending messages or storing
customer details. Do not enter the webhook callback in Meta for the live
business number yet.

The optional send path in `staging_delivery.py` requires a durable PostgreSQL
database. Render's free web service has an ephemeral filesystem and cannot
hold a reliable local SQLite inbox. A free Render Postgres database expires
after 30 days and is only suitable for short testing.

Before a controlled test:

1. Provision a durable PostgreSQL database. Set its private `DATABASE_URL` in
   Render. Use a paid always-on web service before production traffic.
2. Change Render's build command to
   `python -m pip install -r requirements.txt && python -m compileall -q app.py staging_delivery.py`.
3. Set `WA_ACCESS_TOKEN` to a Meta token with the required messaging access,
   `WA_PHONE_NUMBER_ID` to the **test** business phone ID, and
   `WA_GRAPH_VERSION` to the Meta Graph API version in that test app.
4. Set `WA_ALLOWED_TEST_RECIPIENTS` to comma-separated, international-format
   digits for explicit test recipients only (for example `233...`). No `+`.
5. After confirming those settings and the Meta test number, set
   `WA_SEND_ENABLED=1` in the staging service. The existing
   `META_APP_SECRET` and `WA_VERIFY_TOKEN` must remain private.
6. Test one inbound catalog question and a repeated copy of the same signed
   event. Check that exactly one outbound message is recorded. Test STOP,
   human handoff, payment confirmation, and unlisted recipients: none should
   produce an automatic reply.

The database stores an inbound message ID, sender, business phone ID, intent,
state and optional outgoing Meta message ID. It does **not** store the body or
draft. If a Meta send attempt fails or times out, the row becomes `review`.
Never automatically resend it: Meta might have accepted the original request.
`suppressed` rows require operator handling for human and payment requests.
There is no operator inbox or automatic retry worker yet.

The sender allowlist and matching business phone ID are required even when
`WA_SEND_ENABLED=1`; a missing setting returns 503. The Meta callback and API
subdomain DNS remain unchanged until end-to-end test delivery and production
readiness are established.
