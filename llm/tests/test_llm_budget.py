import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))
import picker  # noqa: E402

P1 = {"name": "llm1", "base": "http://a/v1", "key": "k1", "gen": "gen-a", "judge": "judge-a"}


def resp(status, text="", content="{}"):
    r = mock.Mock()
    r.status_code, r.ok, r.text = status, status < 400, text
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


class BudgetRetryTests(unittest.TestCase):
    def setUp(self):
        picker._cooldown.clear()

    def test_retries_once_with_bigger_budget_when_model_runs_out_of_tokens(self):
        bodies = []
        seq = [resp(400, '{"failed_generation":"max completion tokens reached before generating a valid document"}'),
               resp(200, content="fine")]

        def fake_post(url, **kw):
            bodies.append(kw["json"]["max_completion_tokens"])
            return seq.pop(0)

        with mock.patch.object(picker.config, "providers", return_value=[P1]), \
                mock.patch.object(picker.requests, "post", side_effect=fake_post):
            self.assertEqual(picker.ask_llm("hi", role="judge"), "fine")
        self.assertEqual(bodies[0], 4000)
        self.assertGreater(bodies[1], 4000)       # the retry gets a bigger allowance...
        self.assertLessEqual(bodies[1], 8000)     # ...but never more than the provider's per-minute limit allows

    def test_output_allowance_shrinks_for_a_big_prompt_and_refuses_an_impossible_one(self):
        seen = []

        def fake_post(url, **kw):
            seen.append(kw["json"]["max_completion_tokens"])
            return resp(200, content="{}")

        big = "x" * 16000                         # about 4,800 tokens
        with mock.patch.object(picker.config, "providers", return_value=[P1]), \
                mock.patch.object(picker.requests, "post", side_effect=fake_post):
            picker.ask_llm(big)
            self.assertLess(seen[0], 4000)
            self.assertGreaterEqual(seen[0], picker.MIN_OUT)
            with self.assertRaises(RuntimeError) as cm:
                picker.ask_llm("y" * 30000)       # about 8,900 tokens: cannot fit in 8000 at all
            self.assertIn("too large", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
