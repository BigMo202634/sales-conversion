# OIM staging catalog update

For `BigMo202634/sales-conversion` at commit
`14d2649ce1cf98d6f092e12f560c53f5205cf07c`:

- Add `oim_catalog.py` and `test_oim_catalog.py` at the repository root.
- Replace root `webhook_logic.py` and `test_webhook_logic.py`.
- Leave `app.py` and the other files in place.
- Run `python -m unittest -v test_app.py test_webhook_http.py test_webhook_logic.py test_oim_catalog.py`.

The catalog quotes the user-supplied retail prices in GHS for OIM_BOSS,
OIM_BILLONAIRE, OIM_ALPHA, OIM_SEDUCTION and OIM_MIRAYA. It explains free
delivery within Kumasi for orders of GH₵200 or more. Availability, delivery
timing and payment confirmation still require a human check.

The MoMo account is not in source control. If drafts should display it, set
`OIM_MOMO_NUMBER` and `OIM_MOMO_NAME` in Render's Environment page.

This remains draft-only staging code. It does not send, store or log customer
messages. Do not connect a live business phone number yet.
