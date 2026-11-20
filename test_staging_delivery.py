import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock, patch

from fixtures import (CUSTOMER_IGSID, IG_ID, messaging_event, sample_businesses,
                      whatsapp_event)
from staging_delivery import ConfigurationError, process, send_enabled, settings

ENV = {"DATABASE_URL": "test-db", "GRAPH_VERSION": "v27.0",
       "WA_ACCESS_TOKEN": "wa-token", "OIM_PAGE_ACCESS_TOKEN": "page-token"}
BUSINESSES = sample_businesses()


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, statement, params=()):
        self.rowcount = 0
        if statement.startswith("INSERT"):
            key = params[:2]
            if key not in self.db.rows:
                self.db.rows[key] = {"business": params[2], "state": params[6],
                                     "outgoing": None}
                self.rowcount = 1
        elif statement.startswith("UPDATE"):
            row = self.db.rows[tuple(params[-2:])]
            if "state = 'attempted'" in statement:
                if row["state"] == "pending":
                    row["state"] = "attempted"
                    self.rowcount = 1
            elif "state = 'review'" in statement:
                row["state"] = "review"
            else:
                row["state"] = "sent"
                row["outgoing"] = params[0]


class FakeDB:
    def __init__(self):
        self.rows = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass


def run(payload, send, db, env=ENV):
    process(payload, settings(env), BUSINESSES, connect=lambda _: db, send=send, env=env)


class StagingDeliveryTests(unittest.TestCase):
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

    def test_one_send_attempt_for_duplicate_event(self):
        db, send = FakeDB(), Mock(return_value="wamid.out")
        for _ in range(2):
            run(whatsapp_event("OIM BOSS 6ml"), send, db)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1], "wa-token")
        self.assertEqual(db.rows[("whatsapp", "wamid.123")],
                         {"business": "oim-fragrance", "state": "sent", "outgoing": "wamid.out"})

    def test_current_render_settings_keep_working(self):
        db, send = FakeDB(), Mock(return_value="wamid.out")
        env = {"DATABASE_URL": "db", "WA_GRAPH_VERSION": "v25.0", "WA_ACCESS_TOKEN": "wa-token",
               "WA_ALLOWED_TEST_RECIPIENTS": "2348000000001"}
        run(whatsapp_event("Boss 6ml", sender="2348000000001"), send, db, env=env)
        send.assert_called_once()

    def test_failed_send_logs_meta_error_without_customer_data(self):
        import io
        from urllib.error import HTTPError
        body = io.BytesIO(json.dumps({"error": {"code": 190, "type": "OAuthException",
                                                "message": "Session has expired"}}).encode())
        failure = HTTPError("https://graph.facebook.com", 401, "Unauthorized", {}, body)
        db, stderr = FakeDB(), io.StringIO()
        with patch("sys.stderr", stderr):
            run(whatsapp_event("OIM BOSS 6ml"), Mock(side_effect=failure), db)
        line = json.loads(stderr.getvalue().strip().splitlines()[-1])
        self.assertEqual((line["event"], line["code"], line["http_status"]),
                         ("send_failed", 190, 401))
        self.assertNotIn("233123456789", stderr.getvalue())
        self.assertNotIn("BOSS", stderr.getvalue())

    def test_instagram_uses_page_token(self):
        db, send = FakeDB(), Mock(return_value="m_out")
        run(messaging_event("instagram", "Boss 6ml", sender=CUSTOMER_IGSID, account=IG_ID),
            send, db)
        self.assertEqual(send.call_args.args[1], "page-token")
        self.assertEqual(db.rows[("instagram", "m_123")]["state"], "sent")

    def test_ambiguous_send_failure_is_not_retried(self):
        db, send = FakeDB(), Mock(side_effect=TimeoutError("ambiguous"))
        for _ in range(2):
            run(whatsapp_event("OIM BOSS 6ml"), send, db)
        send.assert_called_once()
        self.assertEqual(db.rows[("whatsapp", "wamid.123")]["state"], "review")

    def test_unlisted_sender_missing_token_and_handoff_never_send(self):
        db, send = FakeDB(), Mock()
        run(whatsapp_event(sender="233000000000"), send, db)
        run(messaging_event("page"), send, db,
            env={k: v for k, v in ENV.items() if k != "OIM_PAGE_ACCESS_TOKEN"})
        self.assertFalse(db.rows)
        run(whatsapp_event("I want a human"), send, db)
        self.assertEqual(db.rows[("whatsapp", "wamid.123")]["state"], "suppressed")
        send.assert_not_called()

    def test_http_requires_flag_for_delivery(self):
        from test_webhook_http import invoke
        body = json.dumps(whatsapp_event()).encode()
        sig = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        with patch.dict("os.environ", {"META_APP_SECRET": "test-app-secret",
                                       "SEND_ENABLED": "1"}), patch("app.process") as delivery:
            result = invoke("POST", "/webhook", body, {"X-Hub-Signature-256": "sha256=" + sig})
        self.assertEqual(result, (200, b"ok"))
        delivery.assert_called_once()


if __name__ == "__main__":
    unittest.main()
