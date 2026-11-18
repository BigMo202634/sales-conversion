# AI Sales Conversion Agent — Offline MVP 0.1
A small, dependency-free **prototype**, not a deployed AI or live WhatsApp integration. It demonstrates deterministic lead-intent routing and safe response rules, with two reusable SKILL.md packages.

## Run
Requires Python 3.10+.
```bash
python agent.py perfume-beauty
python agent.py fashion
python -m unittest discover -s tests -v
```

## Limitations
No LLM, persistent conversation history, catalog database, API integration, follow-up scheduler, authentication, opt-in records or analytics. Responses are templates, not trained AI. This prototype does not send messages or connect to Meta.

## Production milestones
1. Validate customer workflow and obtain test catalog, approved FAQs and sales tone.
2. Add database and deterministic conversation state machine, verified product retrieval, event audit logs, handoff and opt-out records.
3. Add LLM with schema-validated outputs, safety policies and evals for both industries.
4. Connect official WhatsApp Cloud API after business onboarding and test webhooks, messaging windows and template approvals.
5. Add approved follow-up queue, human takeover and verified sales attribution.
6. Add Instagram Messaging and Messenger through eligible official APIs.

Do not impersonate a human or bypass platform disclosure rules. Never fabricate stock, price, delivery, discount or payment confirmation.

## Milestone 2 — local conversation persistence and sales controls
Added `store.py` (SQLite), `engine.py` (tenant-scoped orchestration), `demo.py` and additional tests. Run from this directory:
```bash
python -m unittest discover -s tests -v
python demo.py
```
Features: persisted conversations and message drafts, tenant-scoped verified catalog, intent/action audit events, opt-out suppression, human handoff and explicit resumption. All outgoing responses are **drafts only**; no real messages are sent. `Store('sales.db')` persists locally; the demo uses memory-only SQLite.

**Not production ready:** no LLM, no verified payment integrations, no Meta API, no authentication, no encryption-at-rest, no inbound webhook verification, no idempotency, no real consent ledger, no approved-template follow-up scheduling, no analytics attribution. Never send messages from this demo to real customers. Human handoff can be resumed by the operator only; opted-out status cannot be reset by this API.
