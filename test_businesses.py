import json
import unittest

import businesses as business_config
from businesses import BusinessConfigError, find, load, parse
from fixtures import FASHION_ENTRY, PAGE_ID, WA_PHONE_ID, oim_entry, sample_businesses


class BusinessConfigTests(unittest.TestCase):
    def test_repo_config_loads(self):
        self.assertIn("oim-fragrance", load({}))

    def test_env_json_overrides_file(self):
        loaded = load({"BUSINESSES_JSON": json.dumps([FASHION_ENTRY])})
        self.assertEqual(list(loaded), ["ada-styles"])

    def test_find_routes_by_channel_account(self):
        businesses = sample_businesses()
        self.assertEqual(find(businesses, "whatsapp", WA_PHONE_ID).id, "oim-fragrance")
        self.assertEqual(find(businesses, "messenger", PAGE_ID).id, "oim-fragrance")
        self.assertEqual(find(businesses, "whatsapp", "987654321").id, "ada-styles")
        self.assertIsNone(find(businesses, "whatsapp", PAGE_ID))
        self.assertIsNone(find(businesses, "instagram", ""))

    def test_rejects_shared_accounts_and_bad_entries(self):
        clash = {**FASHION_ENTRY, "channels": {"whatsapp": WA_PHONE_ID}}
        with self.assertRaises(BusinessConfigError):
            parse([oim_entry(), clash])
        with self.assertRaises(BusinessConfigError):
            parse([oim_entry(), oim_entry()])
        with self.assertRaises(BusinessConfigError):
            parse([{**FASHION_ENTRY, "industry": "unknown"}])
        with self.assertRaises(BusinessConfigError):
            parse([{**FASHION_ENTRY, "id": "Bad Id"}])
        with self.assertRaises(BusinessConfigError):
            parse([oim_entry(test_recipients={"whatsapp": ["+233 12"]})])

    def test_secrets_resolve_from_named_env_vars_only(self):
        oim = sample_businesses()["oim-fragrance"]
        self.assertEqual(oim.secret("whatsapp_token", {"OIM_WA_ACCESS_TOKEN": "t"}), "t")
        self.assertEqual(oim.secret("whatsapp_token", {}), "")
        self.assertEqual(oim.secret("not_configured", {"x": "y"}), "")


if __name__ == "__main__":
    unittest.main()
