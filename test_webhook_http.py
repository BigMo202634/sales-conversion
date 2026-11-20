import hashlib
import hmac
import io
import json
import os
import unittest
from unittest.mock import patch

from app import Handler
from fixtures import messaging_event, whatsapp_event as event


def invoke(method, path, body=b"", headers=None):
    """Exercise the handler without opening a socket."""
    handler = object.__new__(Handler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(body)), **(headers or {})}
    handler.rfile = io.BytesIO(body)
    response = []
    handler.respond = lambda status, data=b"", content_type=None: response.append((status, data))
    getattr(handler, "do_" + method)()
    return response[0]


class WebhookHTTPTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"WA_VERIFY_TOKEN": "test-verification",
                                          "META_APP_SECRET": "test-app-secret"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_challenge_and_health(self):
        self.assertEqual(invoke("GET", "/health"), (200, b"ok"))
        query = "/webhook?hub.mode=subscribe&hub.verify_token=test-verification&hub.challenge=123"
        self.assertEqual(invoke("GET", query), (200, b"123"))
        self.assertEqual(invoke("GET", query.replace("test-verification", "wrong")), (403, b""))

    def test_only_signed_events_reach_draft_logic(self):
        body = json.dumps(event()).encode()
        signature = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
        with patch("app.draft_replies") as draft:
            self.assertEqual(invoke("POST", "/webhook", body,
                                    {"X-Hub-Signature-256": "sha256=" + signature}), (200, b"ok"))
            draft.assert_called_once_with(event())
            self.assertEqual(invoke("POST", "/webhook", body,
                                    {"X-Hub-Signature-256": "sha256=" + "0" * 64}), (403, b""))
            draft.assert_called_once()

    def test_messenger_and_instagram_objects_accepted(self):
        def signed(payload):
            body = json.dumps(payload).encode()
            sig = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
            return body, {"X-Hub-Signature-256": "sha256=" + sig}
        with patch("app.draft_replies") as draft:
            for obj in ("page", "instagram"):
                self.assertEqual(invoke("POST", "/webhook", *signed(messaging_event(obj))),
                                 (200, b"ok"))
            self.assertEqual(draft.call_count, 2)
            self.assertEqual(invoke("POST", "/webhook", *signed({"object": "user"})),
                             (400, b""))


if __name__ == "__main__":
    unittest.main()
