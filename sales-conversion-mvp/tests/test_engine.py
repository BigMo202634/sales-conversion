import unittest
from engine import SalesEngine
from store import Store

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.store=Store()
        self.agent=SalesEngine(self.store)
        self.store.upsert_product('shop-a','P1','Amber Mist',25000,True)
        self.store.upsert_product('shop-b','P1','Different Product',45000,False)
    def ask(self,text,business='shop-a',customer='buyer',sku='P1'):
        return self.agent.process(business,customer,'perfume-beauty',text,sku)
    def test_catalog_and_tenant_isolation(self):
        self.assertIn('₦25,000',self.ask('What is the price?')['reply'])
        self.assertIn('₦45,000',self.ask('What is the price?',business='shop-b')['reply'])
    def test_missing_catalog_no_invention(self):
        self.assertNotIn('₦',self.ask('How much?',sku='missing')['reply'])
    def test_optout_persists(self):
        self.assertEqual(self.ask('STOP')['status'],'opted_out')
        self.assertFalse(self.ask('Price please')['send_allowed'])
        self.assertEqual(len(self.store.history('shop-a','buyer')),3)
    def test_handoff_persists_and_resume(self):
        self.assertEqual(self.ask('I need a human')['status'],'human_handoff')
        self.assertEqual(self.ask('Price please')['action'],'await_human')
        self.agent.resume_from_handoff('shop-a','buyer')
        self.assertTrue(self.ask('Price please')['send_allowed'])
    def test_payment_requires_verification(self):
        self.assertEqual(self.ask('I have paid')['action'],'verify_payment')
    def test_event_log(self):
        self.ask('Price please')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
    def test_invalid_price(self):
        with self.assertRaises(ValueError): self.store.upsert_product('a','b','c',-1,True)

if __name__=='__main__': unittest.main()
