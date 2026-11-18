# Sales Conversion Agent webhook staging

This service is a safe staging ingress for Meta WhatsApp Cloud API. It serves
`GET /health`, validates Meta's `GET /webhook` subscription challenge, and
checks the `X-Hub-Signature-256` HMAC on `POST /webhook`.

**It currently acknowledges valid events without processing, storing, or replying to messages.**
Do not use it as the callback for a live business phone number until the sales
engine, durable event processing, and operator handoff are integrated.

## Render Web Service

- Source: this repository
- Runtime: Python
- Build command: `python -m compileall -q app.py`
- Start command: `python app.py`
- Health check path: `/health`
- Environment variables: `WA_VERIFY_TOKEN` (random private value), `META_APP_SECRET`

Never commit secrets. The service starts with no secrets but rejects all webhook
verification and event requests until both values are configured. Render supplies
`PORT`. Test with `python -m unittest -v`.

After deployment, use Render's HTTPS service URL for a staging Meta test app.
Add `api.thescribenetwork.com` as a custom domain only after the service is
verified; change only the `api` DNS record, leaving the main website DNS alone.
