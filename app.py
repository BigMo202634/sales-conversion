"""Staging WhatsApp webhook receiver. It never sends customer messages."""

import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

MAX_BODY_BYTES = 1024 * 1024


def verify_challenge(query, expected_token):
    params = parse_qs(query, keep_blank_values=True)
    mode = params.get("hub.mode", [""])[0]
    token = params.get("hub.verify_token", [""])[0]
    challenge = params.get("hub.challenge", [""])[0]
    if not expected_token or mode != "subscribe" or not challenge:
        return None
    return challenge if hmac.compare_digest(token, expected_token) else None


def verify_signature(body, header, app_secret):
    if not app_secret or not header.startswith("sha256="):
        return False
    supplied = header.removeprefix("sha256=")
    if len(supplied) != 64:
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body=b"", content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == "/health":
            return self.respond(200, b"ok")
        if path.path != "/webhook":
            return self.respond(404)
        token = os.environ.get("WA_VERIFY_TOKEN", "")
        challenge = verify_challenge(path.query, token)
        if challenge is None:
            return self.respond(403)
        return self.respond(200, challenge.encode("utf-8"))

    def do_POST(self):
        if urlsplit(self.path).path != "/webhook":
            return self.respond(404)
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.respond(400)
        if length < 0 or length > MAX_BODY_BYTES:
            return self.respond(413)
        body = self.rfile.read(length)
        if len(body) != length:
            return self.respond(400)
        if not verify_signature(body, self.headers.get("X-Hub-Signature-256", ""), os.environ.get("META_APP_SECRET", "")):
            return self.respond(403)
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self.respond(400)
        if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
            return self.respond(400)
        # Staging only: acknowledge verified events without storing or sending messages.
        return self.respond(200, b"ok")

    def log_message(self, format, *args):
        # Avoid logging URL query tokens, payloads, or customer identifiers.
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
