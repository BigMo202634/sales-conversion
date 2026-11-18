"""SQLite persistence for local MVP. Not a hosted multi-tenant production store."""
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = '''
CREATE TABLE IF NOT EXISTS conversations (business_id TEXT NOT NULL, customer_id TEXT NOT NULL, industry TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', last_intent TEXT, last_inbound_at TEXT, updated_at TEXT NOT NULL, PRIMARY KEY(business_id, customer_id));
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id TEXT NOT NULL, customer_id TEXT NOT NULL, direction TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (business_id TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL, price_ngn INTEGER NOT NULL CHECK(price_ngn >= 0), in_stock INTEGER NOT NULL CHECK(in_stock IN (0,1)), details TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(business_id, sku));
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, business_id TEXT NOT NULL, customer_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
'''

def now(): return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path=':memory:'):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
    def upsert_product(self, business_id, sku, name, price_ngn, in_stock, details=None):
        if not isinstance(price_ngn, int) or isinstance(price_ngn,bool) or price_ngn < 0: raise ValueError('price_ngn must be a nonnegative integer')
        self.db.execute('INSERT INTO products VALUES (?,?,?,?,?,?) ON CONFLICT(business_id,sku) DO UPDATE SET name=excluded.name,price_ngn=excluded.price_ngn,in_stock=excluded.in_stock,details=excluded.details', (business_id,sku,name,price_ngn,int(bool(in_stock)),json.dumps(details or {})))
        self.db.commit()
    def product(self, business_id, sku):
        row=self.db.execute('SELECT * FROM products WHERE business_id=? AND sku=?',(business_id,sku)).fetchone()
        return dict(row) if row else None
    def conversation(self, business_id, customer_id):
        row=self.db.execute('SELECT * FROM conversations WHERE business_id=? AND customer_id=?',(business_id,customer_id)).fetchone()
        return dict(row) if row else None
    def save_conversation(self,business_id,customer_id,industry,status,intent):
        timestamp=now()
        self.db.execute('INSERT INTO conversations(business_id,customer_id,industry,status,last_intent,last_inbound_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(business_id,customer_id) DO UPDATE SET status=excluded.status,last_intent=excluded.last_intent,last_inbound_at=excluded.last_inbound_at,updated_at=excluded.updated_at', (business_id,customer_id,industry,status,intent,timestamp,timestamp))
        self.db.commit()
    def message(self,business_id,customer_id,direction,body):
        self.db.execute('INSERT INTO messages(business_id,customer_id,direction,body,created_at) VALUES(?,?,?,?,?)',(business_id,customer_id,direction,body,now()))
        self.db.commit()
    def event(self,business_id,customer_id,event_type,payload=None):
        self.db.execute('INSERT INTO events(business_id,customer_id,event_type,payload,created_at) VALUES(?,?,?,?,?)',(business_id,customer_id,event_type,json.dumps(payload or {}),now()))
        self.db.commit()
    def history(self,business_id,customer_id):
        return [dict(x) for x in self.db.execute('SELECT direction,body,created_at FROM messages WHERE business_id=? AND customer_id=? ORDER BY id',(business_id,customer_id))]
