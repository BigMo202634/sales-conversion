"""Public privacy policy and data deletion pages that Meta asks for.

The operator name and contact address come from PRIVACY_OPERATOR and
PRIVACY_CONTACT so they can be changed in Render without a code change.
"""

import html
import os

DEFAULT_OPERATOR = "The Scribe Network"


def _shell(title, body):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:720px;
margin:0 auto;padding:24px 16px 64px;line-height:1.6;color:#1d1d1f;background:#fff}}
h1{{font-size:1.6rem}} h2{{font-size:1.15rem;margin-top:2rem}}
@media (prefers-color-scheme:dark){{body{{color:#eee;background:#141414}} a{{color:#8ab4ff}}}}
</style></head><body>{body}</body></html>"""


def _who(env):
    operator = html.escape(env.get("PRIVACY_OPERATOR") or DEFAULT_OPERATOR)
    contact = html.escape(env.get("PRIVACY_CONTACT", ""))
    reach = (f'email <a href="mailto:{contact}">{contact}</a>' if contact
             else "message the business you chatted with")
    return operator, reach


def privacy(env):
    operator, reach = _who(env)
    return _shell("Privacy policy", f"""
<h1>Privacy policy</h1>
<p>{operator} runs an automated sales assistant that answers customer messages
on WhatsApp, Instagram and Facebook Messenger on behalf of the businesses that
use it. This page explains what happens to your messages.</p>
<h2>What we receive</h2>
<p>When you message a business that uses our assistant, Meta sends us your
message text, your WhatsApp number or your Instagram/Messenger account ID, and
message IDs. We do not receive your contacts, photos or other chats.</p>
<h2>How we use it</h2>
<ul>
<li>To answer your questions about the business's products, prices and delivery.</li>
<li>To pass your order or question to the business owner when a person needs to step in.</li>
<li>To avoid answering the same message twice.</li>
</ul>
<p>Message text is processed by an AI language model provider to write
replies. We do not sell your data or use it for advertising.</p>
<h2>How long we keep it</h2>
<p>Conversation text is deleted after 7 days. Message IDs and delivery status are
kept for record keeping. The business you messaged also sees your messages in
its own WhatsApp, Instagram or Messenger account under its own policies.</p>
<h2>Your choices</h2>
<p>Reply <b>STOP</b> to stop follow-up messages. Send <b>delete my data</b> in
the chat to erase your saved conversation, or see
<a href="/data-deletion">data deletion</a>. For any other question, {reach}.</p>
""")


def data_deletion(env):
    operator, reach = _who(env)
    return _shell("Data deletion", f"""
<h1>Delete your data</h1>
<p>To delete the conversation {operator} has stored for you, send the message
<b>delete my data</b> in the same WhatsApp, Instagram or Messenger chat. Your
saved messages are erased straight away and you get a confirmation.</p>
<p>If you can't use the chat, {reach} with the number or account you messaged
from, and we will delete your data within 30 days.</p>
<p><a href="/privacy">Privacy policy</a></p>
""")


PAGES = {"/privacy": privacy, "/data-deletion": data_deletion}


def render(path, env=None):
    return PAGES[path](os.environ if env is None else env)
