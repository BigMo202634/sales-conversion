"""Run: python demo.py"""
from store import Store
from engine import SalesEngine

store=Store()
store.upsert_product('demo-beauty','M50','Amber Mist 50ml',25000,True)
store.upsert_product('demo-fashion','F12','Relaxed Two-Piece',38000,True,{'sizes':['M','L']})
engine=SalesEngine(store)
for shop,industry,sku,queries in [
    ('demo-beauty','perfume-beauty','M50',['How much is this perfume?','That is expensive','Can you deliver tomorrow?']),
    ('demo-fashion','fashion','F12',['Is this available?','Will medium fit?','I need a human'])]:
    print('\n',shop)
    for query in queries:
        result=engine.process(shop,'customer-1',industry,query,sku)
        print('Customer:',query,'\nAgent draft:',result['reply'],'\nAction:',result['action'])
