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
        # Any one of several client apps may sign the event.
        self.assertTrue(verify_signature(body, "sha256=" + digest, ["other", "app-secret"]))
        self.assertFalse(verify_signature(body, "sha256=" + digest, ["other", ""]))

    def test_app_secrets_include_each_business_app(self):
        import json
        from app import app_secrets
        from fixtures import oim_entry
        entry = oim_entry()
        entry["secrets"]["app_secret"] = "OIM_META_APP_SECRET"
        env = {"META_APP_SECRET": "main", "OIM_META_APP_SECRET": "client",
               "BUSINESSES_JSON": json.dumps([entry])}
        self.assertEqual(app_secrets(env), ["main", "client"])

    def test_privacy_pages(self):
        import pages
        privacy = pages.render("/privacy", {"PRIVACY_OPERATOR": "Acme <Ltd>",
                                            "PRIVACY_CONTACT": "privacy@example.com"})
        self.assertIn("Acme &lt;Ltd&gt;", privacy)
        self.assertIn("mailto:privacy@example.com", privacy)
        self.assertIn("delete my data", pages.render("/data-deletion", {}))


if __name__ == "__main__":
    unittest.main()
