"""Delivery tests against a real PostgreSQL database.

Set TEST_DATABASE_URL to an empty scratch database to run them, e.g.
TEST_DATABASE_URL=postgresql://postgres@localhost:5433/postgres python -m unittest
Every test drops and recreates the tables it uses.
"""

import hashlib
import hmac
import io
import json
import os
import unittest
from itertools import count
from unittest.mock import Mock, patch

from fixtures import (CUSTOMER_IGSID, CUSTOMER_WA, IG_ID, WA_PHONE_ID, messaging_event,
                      sample_businesses, whatsapp_event)
from staging_delivery import (ConfigurationError, process, send_enabled, send_reminders,
                              settings)

DB_URL = os.environ.get("TEST_DATABASE_URL", "")
OWNER = "233200000001"
ENV = {"DATABASE_URL": DB_URL or "unused", "GRAPH_VERSION": "v27.0",
       "WA_ACCESS_TOKEN": "wa-token", "OIM_PAGE_ACCESS_TOKEN": "page-token",
       "OIM_OWNER_ALERT_NUMBERS": OWNER}
BUSINESSES = sample_businesses()
READY = {"intent": "ai_ready_to_buy", "action": "ai_handoff", "needs_human": True,
         "share_payment": False, "reply": "Noted! We'll confirm availability shortly."}
CHAT = {"intent": "ai_product", "action": "ai_reply", "needs_human": False,
        "share_payment": False, "reply": "Boss is our best seller. For you or a gift?"}


class FakeMeta:
    """Records sends and hands out message IDs like Meta does."""

    def __init__(self, fail_for=()):
        self.sent = []
        self.ids = count(1)
        self.fail_for = set(fail_for)

    def __call__(self, item, token, config):
        if item["sender"] in self.fail_for:
            raise TimeoutError("ambiguous")
        self.sent.append({**item, "token": token})
        return f"wamid.out{next(self.ids)}"

    def to(self, number):
        return [s for s in self.sent if s["sender"] == number]


def connect(_url):
    import psycopg
    return psycopg.connect(DB_URL)


def run(payload, meta, env=ENV, ai=None):
    with patch("staging_delivery.ai_reply", Mock(return_value=ai)) as ai_mock:
        process(payload, settings(env), BUSINESSES, connect=connect, send=meta, env=env)
    return ai_mock


def query(sql, params=()):
    with connect(None) as db, db.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall() if cursor.description else None


class ConfigTests(unittest.TestCase):
    def test_requires_global_configuration(self):
        self.assertEqual(settings(ENV)["GRAPH_VERSION"], "v27.0")
        self.assertEqual(settings({"DATABASE_URL": "x", "WA_GRAPH_VERSION": "v1.0"})["GRAPH_VERSION"], "v1.0")
        for key in ("DATABASE_URL", "GRAPH_VERSION"):
            with self.assertRaises(ConfigurationError):
                settings({k: v for k, v in ENV.items() if k != key})
        with self.assertRaises(ConfigurationError):
            settings({**ENV, "GRAPH_VERSION": "latest"})
        self.assertTrue(send_enabled({"WA_SEND_ENABLED": "1"}))
        self.assertFalse(send_enabled({}))

    def test_http_requires_flag_for_delivery(self):
        from test_webhook_http import invoke
        body = json.dumps(whatsapp_event()).encode()
        sig = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        with patch.dict("os.environ", {"META_APP_SECRET": "test-app-secret",
                                       "SEND_ENABLED": "1"}), patch("app.process") as delivery:
            result = invoke("POST", "/webhook", body, {"X-Hub-Signature-256": "sha256=" + sig})
        self.assertEqual(result, (200, b"ok"))
        delivery.assert_called_once()

    def test_reminder_endpoint_needs_key(self):
        from test_webhook_http import invoke
        with patch.dict("os.environ", {"TASKS_KEY": "k", "SEND_ENABLED": "1"}), \
                patch("app.send_reminders", return_value=2) as reminders:
            self.assertEqual(invoke("GET", "/tasks/reminders?key=wrong")[0], 403)
            self.assertEqual(invoke("GET", "/tasks/reminders?key=k"), (200, b"ok 2"))
        reminders.assert_called_once()


@unittest.skipUnless(DB_URL, "set TEST_DATABASE_URL to run delivery tests")
class DeliveryTests(unittest.TestCase):
    def setUp(self):
        for table in ("message_inbox", "conversation_messages", "handoffs", "alert_links"):
            query(f"DROP TABLE IF EXISTS {table}")
        self.stderr = io.StringIO()
        patcher = patch("sys.stderr", self.stderr)
        patcher.start()
        self.addCleanup(patcher.stop)

    def state(self, message_id="wamid.123", channel="whatsapp"):
        return query("SELECT state FROM message_inbox WHERE channel = %s AND message_id = %s",
                     (channel, message_id))[0][0]

    def test_one_send_attempt_for_duplicate_event(self):
        meta = FakeMeta()
        for _ in range(2):
            run(whatsapp_event("OIM BOSS 6ml"), meta)
        self.assertEqual(len(meta.sent), 1)
        self.assertEqual(meta.sent[0]["token"], "wa-token")
        self.assertIn("GH₵25", meta.sent[0]["reply"])
        self.assertEqual(self.state(), "sent")

    def test_ambiguous_send_failure_is_not_retried(self):
        meta = FakeMeta(fail_for=[CUSTOMER_WA])
        for _ in range(2):
            run(whatsapp_event("OIM BOSS 6ml"), meta)
        self.assertEqual(self.state(), "review")
        self.assertIn("send_failed", self.stderr.getvalue())

    def test_instagram_uses_page_token(self):
        meta = FakeMeta()
        run(messaging_event("instagram", "Boss 6ml", sender=CUSTOMER_IGSID, account=IG_ID), meta)
        self.assertEqual(meta.sent[0]["token"], "page-token")

    def test_unlisted_sender_and_missing_token_never_send(self):
        meta = FakeMeta()
        run(whatsapp_event(sender="233000000000"), meta)
        run(messaging_event("page"), meta,
            env={k: v for k, v in ENV.items() if k != "OIM_PAGE_ACCESS_TOKEN"})
        self.assertEqual(meta.sent, [])
        self.assertEqual(query("SELECT count(*) FROM message_inbox")[0][0], 0)

    def test_ai_reply_is_sent_and_remembered(self):
        meta = FakeMeta()
        run(whatsapp_event("which perfume lasts long"), meta, ai=CHAT)
        self.assertEqual(meta.sent[0]["reply"], CHAT["reply"])
        ai_mock = run(whatsapp_event("for my husband", message_id="wamid.124"), meta, ai=CHAT)
        history = ai_mock.call_args.args[2]
        self.assertEqual(history[0], {"role": "user", "content": "which perfume lasts long"})
        self.assertEqual(history[1], {"role": "assistant", "content": CHAT["reply"]})

    def test_opt_out_never_replies_or_alerts(self):
        meta = FakeMeta()
        ai_mock = run(whatsapp_event("STOP"), meta, ai=CHAT)
        ai_mock.assert_not_called()
        self.assertEqual(meta.sent, [])
        self.assertEqual(self.state(), "suppressed")

    def test_payment_details_come_from_settings_not_the_ai(self):
        meta = FakeMeta()
        env = {**ENV, "OIM_MOMO_NUMBER": "0240000000", "OIM_MOMO_NAME": "OIM Ventures"}
        run(whatsapp_event("I'll take 2 Boss 3ml, how do I pay?"), meta, env=env)
        self.assertIn("0240000000 (OIM Ventures)", meta.to(CUSTOMER_WA)[0]["reply"])
        meta = FakeMeta()
        ai = {**CHAT, "share_payment": True, "reply": "Great choice! Details are below."}
        run(whatsapp_event("ok sounds good", message_id="wamid.2"), meta, env=env, ai=ai)
        self.assertTrue(meta.sent[0]["reply"].startswith("Great choice! Details are below."))
        self.assertIn("0240000000 (OIM Ventures)", meta.sent[0]["reply"])
        meta = FakeMeta()
        run(whatsapp_event("ok", message_id="wamid.3"), meta, ai=ai)  # no MoMo settings
        self.assertEqual(meta.sent[0]["reply"], "Great choice! Details are below.")

    def test_paid_customer_gets_ack_owner_gets_alert_and_ai_goes_quiet(self):
        meta = FakeMeta()
        run(whatsapp_event("I have paid"), meta, ai=CHAT)
        self.assertIn("verify", meta.to(CUSTOMER_WA)[0]["reply"])
        alert = meta.to(OWNER)[0]
        self.assertIn("paid", alert["reply"])
        self.assertIn("wa.me/" + CUSTOMER_WA, alert["reply"])
        self.assertIn("Swipe-reply", alert["reply"])
        # Customer writes again: forwarded to the owner, no answer from the assistant.
        meta = FakeMeta()
        ai_mock = run(whatsapp_event("hello??", message_id="wamid.2"), meta, ai=CHAT)
        ai_mock.assert_not_called()
        self.assertEqual(meta.to(CUSTOMER_WA), [])
        self.assertIn("Customer replied", meta.to(OWNER)[0]["reply"])
        self.assertIn("hello??", meta.to(OWNER)[0]["reply"])

    def test_owner_swipe_reply_reaches_customer_and_done_hands_back(self):
        meta = FakeMeta()
        run(whatsapp_event("I'll take 2 Boss 3ml"), meta, ai=READY)
        self.assertEqual([s["sender"] for s in meta.sent], [CUSTOMER_WA, OWNER])
        alert_id = "wamid.out2"
        meta = FakeMeta()
        ai_mock = run(whatsapp_event("Hi, it's Mo. Both in stock, which area?", sender=OWNER,
                                     message_id="wamid.o1", reply_to=alert_id), meta, ai=CHAT)
        ai_mock.assert_not_called()
        relay = meta.to(CUSTOMER_WA)[0]
        self.assertEqual((relay["reply"], relay["account_id"], relay["message_id"]),
                         ("Hi, it's Mo. Both in stock, which area?", WA_PHONE_ID, None))
        self.assertEqual(meta.to(OWNER), [])
        # Customer answers the owner: the assistant stays quiet, the owner hears about it.
        meta = FakeMeta()
        ai_mock = run(whatsapp_event("Adum", message_id="wamid.c2"), meta, ai=CHAT)
        ai_mock.assert_not_called()
        self.assertEqual(meta.to(CUSTOMER_WA), [])
        self.assertIn("Adum", meta.to(OWNER)[0]["reply"])
        # Owner hands back with "done" on the new alert.
        meta2 = FakeMeta()
        run(whatsapp_event("Done", sender=OWNER, message_id="wamid.o2", reply_to="wamid.out1"),
            meta2)
        self.assertIn("handling this customer again", meta2.to(OWNER)[0]["reply"])
        meta3 = FakeMeta()
        ai_mock = run(whatsapp_event("thanks!", message_id="wamid.c3"), meta3, ai=CHAT)
        ai_mock.assert_called_once()
        self.assertEqual(meta3.to(CUSTOMER_WA)[0]["reply"], CHAT["reply"])
        # The relayed owner message is part of the assistant's memory.
        contents = [m["content"] for m in ai_mock.call_args.args[2]]
        self.assertIn("Hi, it's Mo. Both in stock, which area?", contents)

    def test_owner_number_without_swipe_reply_is_a_normal_customer(self):
        meta = FakeMeta()
        env = {**ENV, "OIM_OWNER_ALERT_NUMBERS": CUSTOMER_WA}
        ai_mock = run(whatsapp_event("hi"), meta, env=env, ai=CHAT)
        ai_mock.assert_called_once()
        self.assertEqual(meta.sent[0]["reply"], CHAT["reply"])

    def test_alert_failure_does_not_break_reply(self):
        meta = FakeMeta(fail_for=[OWNER])
        run(whatsapp_event("I'll take it"), meta, ai=READY)
        self.assertEqual(self.state(), "sent")
        self.assertIn("alert_failed", self.stderr.getvalue())

    def test_reminders_until_owner_replies(self):
        meta = FakeMeta()
        run(whatsapp_event("I'll take 2"), meta, ai=READY)
        self.assertEqual(send_reminders(settings(ENV), BUSINESSES, connect, meta, ENV), 0)
        query("UPDATE handoffs SET customer_waiting_since = now() - interval '11 minutes'")
        meta = FakeMeta()
        self.assertEqual(send_reminders(settings(ENV), BUSINESSES, connect, meta, ENV), 1)
        self.assertIn("still waiting", meta.to(OWNER)[0]["reply"])
        # Not again straight away, and none once the owner has replied.
        self.assertEqual(send_reminders(settings(ENV), BUSINESSES, connect, meta, ENV), 0)
        query("UPDATE handoffs SET reminded_at = now() - interval '11 minutes'")
        run(whatsapp_event("On it", sender=OWNER, message_id="wamid.o1", reply_to="wamid.out1"),
            FakeMeta())
        self.assertEqual(send_reminders(settings(ENV), BUSINESSES, connect, FakeMeta(), ENV), 0)

    def test_logs_never_contain_customer_data(self):
        run(whatsapp_event("I have paid for OIM BOSS"), FakeMeta())
        self.assertNotIn(CUSTOMER_WA, self.stderr.getvalue())
        self.assertNotIn("BOSS", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
