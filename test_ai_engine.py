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
                      response("not json"),
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


if __name__ == "__main__":
    unittest.main()
