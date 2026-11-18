import hashlib
import hmac
import unittest

from app import verify_challenge, verify_signature


class WebhookVerificationTests(unittest.TestCase):
    def test_subscription_challenge(self):
        query = "hub.mode=subscribe&hub.verify_token=secret&hub.challenge=12345"
        self.assertEqual(verify_challenge(query, "secret"), "12345")
        self.assertIsNone(verify_challenge(query, "wrong"))
        self.assertIsNone(verify_challenge(query, ""))

    def test_signed_payload(self):
        body = b'{"object":"whatsapp_business_account"}'
        digest = hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_signature(body, "sha256=" + digest, "app-secret"))
        self.assertFalse(verify_signature(body + b" ", "sha256=" + digest, "app-secret"))
        self.assertFalse(verify_signature(body, "sha256=" + digest, ""))


if __name__ == "__main__":
    unittest.main()
