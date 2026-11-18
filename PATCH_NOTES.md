# Staging sales drafts patch

For the existing `BigMo202634/sales-conversion` repository at commit
`487c6a28167b0cf8f46c307e051ec47912de7498`:

- Replace root `app.py`.
- Add root `webhook_logic.py`, `test_webhook_logic.py`, and
  `test_webhook_http.py`.
- Keep the existing `sales-conversion-mvp/agent.py` folder in place.

Run `python -m unittest -v test_app.py test_webhook_logic.py test_webhook_http.py`.

After a valid Meta signature, the webhook extracts inbound text and invokes
the existing offline sales decision prototype. It ignores media and status
events. Drafts are discarded: no message is sent, stored, or logged. This
patch therefore does not make the WhatsApp agent ready for customers.

Before connecting a live phone number, implement durable deduplication,
conversation and opt-out state, a verified business catalog, human takeover,
an outbound queue, and official Cloud API sending credentials. Do not place
secret values in this repository.
