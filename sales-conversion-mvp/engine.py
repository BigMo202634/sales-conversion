"""Auditable offline sales engine with tenant-scoped catalog and opt-out/handoff."""
from agent import reply, classify

class SalesEngine:
    def __init__(self,store): self.store=store
    def process(self,business_id,customer_id,industry,message,sku=None):
        if industry not in ('fashion','perfume-beauty'): raise ValueError('Unsupported industry')
        if not all(isinstance(x,str) and x.strip() for x in (business_id,customer_id,message)): raise ValueError('Required fields missing')
        existing=self.store.conversation(business_id,customer_id)
        intent=classify(message)
        status=existing['status'] if existing else 'active'
        self.store.message(business_id,customer_id,'inbound',message)
        if intent=='opt_out': status='opted_out'
        elif intent=='handoff': status='human_handoff'
        if status=='opted_out' and intent!='opt_out':
            result={'intent':intent,'reply':None,'action':'suppressed_opt_out'}
        elif status=='human_handoff' and intent!='handoff':
            result={'intent':intent,'reply':None,'action':'await_human'}
        else:
            product=self.store.product(business_id,sku) if sku else None
            catalog=({'verified_product':product['name'],'price':product['price_ngn'],'in_stock':bool(product['in_stock'])} if product else None)
            result=reply(message,industry,catalog)
        self.store.save_conversation(business_id,customer_id,industry,status,intent)
        self.store.event(business_id,customer_id,result['action'],{'intent':intent,'sku':sku})
        if result['reply']: self.store.message(business_id,customer_id,'outbound_draft',result['reply'])
        return {**result,'status':status,'send_allowed':bool(result['reply'])}
    def resume_from_handoff(self,business_id,customer_id):
        existing=self.store.conversation(business_id,customer_id)
        if not existing or existing['status']!='human_handoff': raise ValueError('No active handoff')
        self.store.save_conversation(business_id,customer_id,existing['industry'],'active',existing['last_intent'])
        self.store.event(business_id,customer_id,'human_resumed')
