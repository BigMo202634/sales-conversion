import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import ai_engine
from fixtures import sample_businesses

ENV = {"ANTHROPIC_API_KEY": "test-key"}
OIM = sample_businesses()["oim-fragrance"]


def response(data, stop_reason="end_turn"):
    text = data if isinstance(data, str) else json.dumps(data)
    return SimpleNamespace(stop_reason=stop_reason,
                           content=[SimpleNamespace(type="text", text=text)])


def client_returning(value):
    client = Mock()
    if isinstance(value, Exception):
        client.beta.messages.create.side_effect = value
    else:
        client.beta.messages.create.return_value = value
    return client


class AIEngineTests(unittest.TestCase):
    def test_reply_uses_catalog_and_history(self):
        client = client_returning(response(
            {"reply": "OIM_BOSS 30ml is GH₵120. How many?", "intent": "price",
             "needs_human": False}))
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Welcome!"}]
        result = ai_engine.reply("price of boss 30ml", OIM, history, ENV, client)
        self.assertEqual(result, {"intent": "ai_price", "action": "ai_reply",
                                  "reply": "OIM_BOSS 30ml is GH₵120. How many?",
                                  "needs_human": False})
        kwargs = client.beta.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-5-5")
        self.assertEqual(kwargs["messages"][-1], {"role": "user", "content": "price of boss 30ml"})
        self.assertEqual(len(kwargs["messages"]), 3)
        self.assertIn("OIM_BOSS", kwargs["system"])
        self.assertIn("120", kwargs["system"])

    def test_ready_buyer_is_handed_off(self):
        client = client_returning(response(
            {"reply": "Great choice! The team will confirm your order shortly.",
             "intent": "ready_to_buy", "needs_human": True}))
        result = ai_engine.reply("I'll take 2 Boss 30ml", OIM, (), ENV, client)
        self.assertEqual((result["action"], result["needs_human"]), ("ai_handoff", True))

    def test_falls_back_on_problems(self):
        good = {"reply": "ok", "intent": "other", "needs_human": False}
        for value in (response(good, stop_reason="refusal"),
                      response(good, stop_reason="max_tokens"),
                      response('{"reply": broken'),
                      response({**good, "reply": "  "}),
                      TimeoutError("slow")):
            self.assertIsNone(ai_engine.reply("hello", OIM, (), ENV, client_returning(value)))

    def test_disabled_without_key_or_when_switched_off(self):
        client = client_returning(response({"reply": "ok", "intent": "other",
                                            "needs_human": False}))
        self.assertIsNone(ai_engine.reply("hello", OIM, (), {}, client))
        self.assertIsNone(ai_engine.reply("hello", OIM, (), {**ENV, "AI_REPLIES": "0"}, client))
        client.beta.messages.create.assert_not_called()

    def test_model_override(self):
        client = client_returning(response({"reply": "ok", "intent": "other",
                                            "needs_human": False}))
        ai_engine.reply("hello", OIM, (), {**ENV, "AI_MODEL": "claude-sonnet-5-5"}, client)
        self.assertEqual(client.beta.messages.create.call_args.kwargs["model"],
                         "claude-sonnet-5-5")

    def test_openai_compatible_provider(self):
        env = {"AI_PROVIDER": "openai_compatible", "AI_BASE_URL": "http://localhost:11434/v1/",
               "AI_MODEL": "qwen2.5:3b"}
        sent = {}

        def post(url, body, headers):
            sent.update(url=url, body=body, headers=headers)
            content = 'Sure! ```json\n{"reply": "Boss 6ml is GH₵25. For you or a gift?", ' \
                      '"intent": "price", "needs_human": false}\n```'
            return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}

        result = ai_engine.reply("boss 6ml", OIM, (), env, post=post)
        self.assertEqual(result["reply"], "Boss 6ml is GH₵25. For you or a gift?")
        self.assertEqual(sent["url"], "http://localhost:11434/v1/chat/completions")
        self.assertNotIn("Authorization", sent["headers"])
        self.assertIn("OIM_BOSS", sent["body"]["messages"][0]["content"])
        self.assertEqual(sent["body"]["messages"][-1], {"role": "user", "content": "boss 6ml"})

        keyed = {**env, "AI_API_KEY": "free-key"}
        ai_engine.reply("hi", OIM, (), keyed, post=post)
        self.assertEqual(sent["headers"]["Authorization"], "Bearer free-key")
        self.assertNotIn("Python", sent["headers"]["User-Agent"])

    def test_failure_is_logged_without_customer_text(self):
        import io
        from unittest.mock import patch
        from urllib.error import HTTPError
        env = {"AI_PROVIDER": "openai_compatible", "AI_BASE_URL": "http://x/v1", "AI_MODEL": "m"}
        denied = HTTPError("http://x", 403, "Forbidden", {}, io.BytesIO(b"error code: 1010"))
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            ai_engine.reply("my secret message", OIM, (), env, post=Mock(side_effect=denied))
        line = json.loads(stderr.getvalue())
        self.assertEqual((line["event"], line["http_status"], line["detail"]),
                         ("ai_failed", 403, "error code: 1010"))
        self.assertNotIn("secret", stderr.getvalue())

    def test_plain_text_answer_is_used(self):
        env = {"AI_PROVIDER": "openai_compatible", "AI_BASE_URL": "http://x/v1", "AI_MODEL": "m"}
        plain = lambda *_: {"choices": [{"finish_reason": "stop", "message": {
            "content": "I understand! The 6ml is just GH₵25. Want to try that?"}}]}
        result = ai_engine.reply("too expensive", OIM, (), env, post=plain)
        self.assertEqual((result["reply"], result["intent"], result["needs_human"]),
                         ("I understand! The 6ml is just GH₵25. Want to try that?", "ai_other", False))

    def test_openai_compatible_falls_back(self):
        env = {"AI_PROVIDER": "openai_compatible", "AI_BASE_URL": "http://x/v1", "AI_MODEL": "m"}
        cut = lambda *_: {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}
        self.assertIsNone(ai_engine.reply("hi", OIM, (), env, post=cut))
        down = Mock(side_effect=ConnectionRefusedError())
        self.assertIsNone(ai_engine.reply("hi", OIM, (), env, post=down))
        self.assertIsNone(ai_engine.reply("hi", OIM, (), {**env, "AI_MODEL": ""}, post=down))
        down.assert_called_once()


if __name__ == "__main__":
    unittest.main()
