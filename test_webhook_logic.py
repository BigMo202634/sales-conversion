import unittest

from fixtures import (CUSTOMER_IGSID, IG_ID, messaging_event, sample_businesses,
                      whatsapp_event)
from webhook_logic import draft_replies, inbound_messages

BUSINESSES = sample_businesses()


class WebhookLogicTests(unittest.TestCase):
    def test_whatsapp_text_routes_to_business(self):
        draft = draft_replies(whatsapp_event(), BUSINESSES, {})[0]
        self.assertEqual(draft["channel"], "whatsapp")
        self.assertEqual(draft["business_id"], "oim-fragrance")
        self.assertEqual(draft["message_id"], "wamid.123")
        self.assertEqual(draft["intent"], "catalog")

    def test_messenger_and_instagram_route_to_business(self):
        messenger = draft_replies(messaging_event("page", "STOP"), BUSINESSES, {})[0]
        self.assertEqual((messenger["channel"], messenger["action"]),
                         ("messenger", "suppress_followups"))
        instagram = draft_replies(messaging_event("instagram", "Boss 6ml",
                                                  sender=CUSTOMER_IGSID, account=IG_ID),
                                  BUSINESSES, {})[0]
        self.assertEqual(instagram["channel"], "instagram")
        self.assertIn("OIM_BOSS 6ml is GH₵25", instagram["reply"])

    def test_second_business_gets_its_own_replies(self):
        draft = draft_replies(whatsapp_event("hi", phone_id="987654321"), BUSINESSES, {})[0]
        self.assertEqual(draft["business_id"], "ada-styles")
        self.assertIn("Ada Styles", draft["reply"])

    def test_unknown_account_echo_and_non_text_ignored(self):
        self.assertEqual(draft_replies(whatsapp_event(phone_id="000"), BUSINESSES, {}), [])
        self.assertEqual(draft_replies(messaging_event(echo=True), BUSINESSES, {}), [])
        self.assertEqual(draft_replies(whatsapp_event(message_type="image"), BUSINESSES, {}), [])
        self.assertEqual(inbound_messages({"object": "page", "entry": [{"id": "1", "messaging": [
            {"sender": {"id": "2"}, "delivery": {"mids": ["x"]}}]}]}), [])
        self.assertEqual(inbound_messages({"object": "whatsapp_business_account", "entry": [
            {"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}), [])

    def test_invalid_or_oversized_text_ignored(self):
        self.assertEqual(draft_replies(whatsapp_event(body="x" * 4097), BUSINESSES, {}), [])
        self.assertEqual(inbound_messages({"object": "unknown", "entry": []}), [])
        self.assertEqual(inbound_messages([]), [])


if __name__ == "__main__":
    unittest.main()
