import unittest

from oim_catalog import PRODUCTS, SIZE_PRICES_GHS, reply


class OIMCatalogTests(unittest.TestCase):
    def test_exact_catalog_and_retail_prices(self):
        self.assertEqual(len(PRODUCTS), 5)
        self.assertEqual(SIZE_PRICES_GHS, {3: 15, 6: 25, 12: 60, 30: 120})
        quote = reply("How much is OIM MIRAYA 12ml?")
        self.assertIn("OIM_MIRAYA 12ml is GH₵60 retail", quote["reply"])
        self.assertIn("confirm availability", quote["reply"])
        self.assertIn("OIM_BOSS 3ml is GH₵15", reply("Boss 3ml")["reply"])

    def test_delivery_rule_has_location_and_threshold(self):
        delivery = reply("Do you deliver in Kumasi?")
        self.assertIn("GH₵200 or more", delivery["reply"])
        self.assertIn("within Kumasi", delivery["reply"])
        self.assertIn("confirm delivery options", delivery["reply"])

    def test_payment_not_confirmed(self):
        result = reply("I have paid")
        self.assertEqual(result["action"], "verify_payment")
        self.assertIn("verify the payment", result["reply"])

    def test_momo_is_only_injected_at_runtime(self):
        self.assertNotIn("0240867393", reply("What are your MoMo details?")["reply"])
        result = reply("What are your MoMo details?", "test-number", "test-name")
        self.assertIn("test-number (test-name)", result["reply"])
        self.assertIn("verify payment", result["reply"])

    def test_opt_out_and_handoff_actions(self):
        self.assertEqual(reply("STOP")["action"], "suppress_followups")
        self.assertEqual(reply("I need a human")["action"], "human_handoff")


if __name__ == "__main__":
    unittest.main()
