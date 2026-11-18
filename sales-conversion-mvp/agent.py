"""Dependency-free, offline sales-agent decision prototype. Not connected to WhatsApp."""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).parent

def classify(message):
    t = message.lower()
    if re.search(r'\b(stop|unsubscribe|do not message|don.t message)\b', t): return 'opt_out'
    if re.search(r'\b(human|person|owner|manager|agent)\b', t): return 'handoff'
    if re.search(r'\b(paid|payment|transfer|receipt)\b', t): return 'payment'
    if re.search(r'\b(deliver|delivery|ship|shipping|tomorrow|friday)\b', t): return 'delivery'
    if re.search(r'\b(size|fit|medium|large|small|measurements)\b', t): return 'sizing'
    if re.search(r'\b(expensive|costly|discount|budget|cheaper)\b', t): return 'price_objection'
    if re.search(r'\b(price|how much|cost)\b', t): return 'price'
    if re.search(r'\b(available|stock|have this)\b', t): return 'availability'
    return 'general'

def reply(message, industry, catalog=None):
    catalog = catalog or {}
    intent = classify(message)
    if intent == 'opt_out': return {'intent':intent,'reply':'Understood. We won’t send further follow-up messages.','action':'suppress_followups'}
    if intent == 'handoff': return {'intent':intent,'reply':'Certainly. I’ll pass this to the team for a personal response.','action':'human_handoff'}
    if intent == 'payment': return {'intent':intent,'reply':'Thanks for the update. I’ll ask the team to verify the payment before confirming your order.','action':'verify_payment'}
    if intent == 'delivery': return {'intent':intent,'reply':'Which area should we deliver to? I’ll confirm availability and timing before promising a date.','action':'check_delivery'}
    if intent == 'sizing' and industry == 'fashion': return {'intent':intent,'reply':'What size do you usually wear? I can help compare it with the product’s measurements once we confirm the size chart.','action':'request_size_chart'}
    if intent == 'price_objection': return {'intent':intent,'reply':'I understand. What budget are you comfortable with? I can help you compare available options without pressure.','action':'qualify_budget'}
    if intent in ('price','availability'):
        if catalog.get('verified_product') and catalog.get('price') is not None and catalog.get('in_stock') is not None:
            return {'intent':intent,'reply':f"{catalog['verified_product']} is {'available' if catalog['in_stock'] else 'currently out of stock'} at ₦{catalog['price']:,}. Would you like details?",'action':'answer_verified_catalog'}
        return {'intent':intent,'reply':'Which exact product are you interested in? I’ll check the current price and availability.','action':'request_product'}
    if industry == 'perfume-beauty':
        return {'intent':intent,'reply':'Welcome! Are you shopping for an everyday fragrance, a gift, or a special occasion?','action':'qualify_need'}
    return {'intent':intent,'reply':'Welcome! Are you looking for an outfit, shoes, or a bag today?','action':'qualify_need'}

if __name__ == '__main__':
    industry = sys.argv[1] if len(sys.argv)>1 else 'perfume-beauty'
    if industry not in ('perfume-beauty','fashion'): raise SystemExit('Choose perfume-beauty or fashion')
    print('Offline sales agent prototype. Type quit to exit.')
    while True:
        try: msg=input('Customer> ').strip()
        except EOFError: break
        if msg.lower() in ('quit','exit'): break
        print(json.dumps(reply(msg,industry),ensure_ascii=False,indent=2))
