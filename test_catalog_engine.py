import unittest

from catalog_engine import reply
from fixtures import sample_businesses

BUSINESSES = sample_businesses()
OIM = BUSINESSES["oim-fragrance"]
ADA = BUSINESSES["ada-styles"]


def oim(message, env=None):
    return reply(message, OIM, env or {})


class OIMCatalogTests(unittest.TestCase):
    def test_exact_catalog_and_retail_prices(self):
        quote = oim("How much is OIM MIRAYA 12ml?")
        self.assertIn("OIM_MIRAYA 12ml is GH₵60 retail", quote["reply"])
        self.assertIn("confirm availability", quote["reply"])
        self.assertIn("OIM_BOSS 3ml is GH₵15", oim("Boss 3ml")["reply"])
        self.assertIn("OIM_ALPHA 30ml is GH₵120", oim("alpha 30 ml please")["reply"])

    def test_catalog_listing(self):
        result = oim("How much is it?")
        self.assertEqual(result["intent"], "catalog")
        self.assertIn("OIM_MIRAYA", result["reply"])
        self.assertIn("30ml GH₵120", result["reply"])
        self.assertNotIn("in stock", result["reply"])

    def test_size_only_and_product_only(self):
        self.assertIn("12ml retail price is GH₵60", oim("do you have 12ml")["reply"])
        result = oim("Tell me about seduction")
        self.assertEqual(result["action"], "ask_variant")
        self.assertIn("3ml GH₵15", result["reply"])

    def test_delivery_rule_has_location_and_threshold(self):
        delivery = oim("Do you deliver in Kumasi?")
        self.assertIn("GH₵200 or more", delivery["reply"])
        self.assertIn("within Kumasi", delivery["reply"])

    def test_payment_not_confirmed(self):
        result = oim("I have paid")
        self.assertEqual(result["action"], "verify_payment")
        self.assertIn("verify the payment", result["reply"])

    def test_payment_details_only_injected_at_runtime(self):
        self.assertEqual(oim("What are your MoMo details?")["action"], "request_payment_details")
        result = oim("What are your MoMo details?",
                     {"OIM_MOMO_NUMBER": "test-number", "OIM_MOMO_NAME": "test-name"})
        self.assertIn("test-number (test-name)", result["reply"])
        self.assertIn("verify payment", result["reply"])

    def test_opt_out_and_handoff_actions(self):
        self.assertEqual(oim("STOP")["action"], "suppress_followups")
        self.assertEqual(oim("I need a human")["action"], "human_handoff")


class OtherBusinessTests(unittest.TestCase):
    def test_per_product_prices_in_own_currency(self):
        result = reply("How much is the midi dress in L?", ADA, {})
        self.assertIn("Ankara Midi Dress L is ₦27,500", result["reply"])
        self.assertNotIn("GH₵", result["reply"])

    def test_product_without_price_is_never_guessed(self):
        result = reply("price of the tote?", ADA, {})
        self.assertEqual(result["action"], "check_product")
        self.assertNotIn("₦", result["reply"])

    def test_industry_greeting_and_default_delivery(self):
        self.assertIn("Ada Styles", reply("hello", ADA, {})["reply"])
        self.assertIn("confirm delivery", reply("do you deliver to Lekki?", ADA, {})["reply"])
        self.assertIn("Ada Styles team", reply("I want the owner", ADA, {})["reply"])


if __name__ == "__main__":
    unittest.main()
