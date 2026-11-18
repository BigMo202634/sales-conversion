import unittest
from unittest.mock import Mock, patch

from staging_delivery import ConfigurationError, process, settings
from test_webhook_logic import event


CONFIG = {
    "DATABASE_URL": "test-db",
    "WA_ACCESS_TOKEN": "test-token",
    "WA_PHONE_NUMBER_ID": "123456789",
    "WA_GRAPH_VERSION": "v27.0",
    "WA_ALLOWED_TEST_RECIPIENTS": "233123456789",
}


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
            message_id = params[0]
            if message_id not in self.db.rows:
                self.db.rows[message_id] = {"state": params[4], "meta_message_id": None}
                self.rowcount = 1
        elif statement.startswith("UPDATE"):
            row = self.db.rows[params[-1]]
            if "state = 'attempted'" in statement:
                if row["state"] == "pending":
                    row["state"] = "attempted"
                    self.rowcount = 1
            elif "state = 'review'" in statement:
                row["state"] = "review"
            else:
                row["state"] = "sent"
                row["meta_message_id"] = params[0]


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


def inbound(body="OIM BOSS 6ml", sender="233123456789"):
    payload = event(body)
    payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "123456789"
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["from"] = sender
    return payload


class StagingDeliveryTests(unittest.TestCase):
    def test_requires_complete_explicit_test_configuration(self):
        self.assertEqual(settings(CONFIG)["recipients"], {"233123456789"})
        for key in CONFIG:
            with self.assertRaises(ConfigurationError):
                settings({k: v for k, v in CONFIG.items() if k != key})
        with self.assertRaises(ConfigurationError):
            settings({**CONFIG, "WA_ALLOWED_TEST_RECIPIENTS": "*"})

    def test_one_send_attempt_for_duplicate_event(self):
        db, send = FakeDB(), Mock(return_value="wamid.out")
        for _ in range(2):
            process(inbound(), settings(CONFIG), connect=lambda _: db, send=send)
        send.assert_called_once()
        self.assertEqual(db.rows["wamid.123"],
                         {"state": "sent", "meta_message_id": "wamid.out"})

    def test_ambiguous_send_failure_is_not_retried(self):
        db, send = FakeDB(), Mock(side_effect=TimeoutError("ambiguous"))
        for _ in range(2):
            process(inbound(), settings(CONFIG), connect=lambda _: db, send=send)
        send.assert_called_once()
        self.assertEqual(db.rows["wamid.123"]["state"], "review")

    def test_unlisted_number_and_handoff_never_send(self):
        db, send = FakeDB(), Mock()
        process(inbound(sender="233000000000"), settings(CONFIG),
                connect=lambda _: db, send=send)
        self.assertFalse(db.rows)
        process(inbound(body="I want a human"), settings(CONFIG),
                connect=lambda _: db, send=send)
        self.assertEqual(db.rows["wamid.123"]["state"], "suppressed")
        send.assert_not_called()

    def test_http_requires_flag_for_delivery(self):
        import hashlib
        import hmac
        import json
        from test_webhook_http import invoke
        body = json.dumps(inbound()).encode()
        sig = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        with patch.dict("os.environ", {"META_APP_SECRET": "test-app-secret",
                                    "WA_SEND_ENABLED": "1"}), patch("app.process") as delivery:
            result = invoke("POST", "/webhook", body,
                            {"X-Hub-Signature-256": "sha256=" + sig})
        self.assertEqual(result, (200, b"ok"))
        delivery.assert_called_once()


if __name__ == "__main__":
    unittest.main()
