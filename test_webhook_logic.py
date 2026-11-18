import unittest

from webhook_logic import draft_replies, text_messages


def event(body="How much is it?", message_type="text"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "business-phone"},
                    "messages": [{
                        "id": "wamid.123",
                        "from": "customer",
                        "type": message_type,
                        "text": {"body": body},
                    }],
                }
            }]
        }],
    }


class WebhookLogicTests(unittest.TestCase):
    def test_text_creates_oim_catalog_draft(self):
        draft = draft_replies(event())[0]
        self.assertEqual(draft["message_id"], "wamid.123")
        self.assertEqual(draft["phone_number_id"], "business-phone")
        self.assertEqual(draft["intent"], "catalog")
        self.assertIn("OIM_MIRAYA", draft["reply"])
        self.assertIn("30ml GH₵120", draft["reply"])
        self.assertNotIn("in stock", draft["reply"])

    def test_opt_out_draft(self):
        draft = draft_replies(event("STOP"))[0]
        self.assertEqual(draft["action"], "suppress_followups")

    def test_non_message_events_do_not_create_drafts(self):
        self.assertEqual(text_messages({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}), [])
        self.assertEqual(draft_replies(event(message_type="image")), [])

    def test_invalid_or_oversized_text_ignored(self):
        self.assertEqual(draft_replies(event(body="x" * 4097)), [])
        self.assertEqual(text_messages({"entry": [{"changes": [{"value": {"messages": [{"type": "text"}]}}]}]}), [])

    def test_rejects_unsupported_industry(self):
        with self.assertRaises(ValueError):
            draft_replies(event(), "unknown")


if __name__ == "__main__":
    unittest.main()
