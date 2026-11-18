import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import classify,reply
class TestAgent(unittest.TestCase):
 def test_optout(self): self.assertEqual(reply('Stop messaging me','fashion')['action'],'suppress_followups')
 def test_no_invented_price(self): self.assertNotIn('₦',reply('How much?','fashion')['reply'])
 def test_verified_price(self): self.assertIn('₦25,000',reply('How much?','fashion',{'verified_product':'Bag','price':25000,'in_stock':True})['reply'])
 def test_payment_handoff(self): self.assertEqual(reply('I paid','fashion')['action'],'verify_payment')
 def test_size(self): self.assertEqual(classify('Is medium size okay?'),'sizing')
if __name__=='__main__': unittest.main()
