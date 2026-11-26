import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))
import picker  # noqa: E402

P1 = {"name": "llm1", "base": "http://a/v1", "key": "k1", "gen": "gen-a", "judge": "judge-a"}
P2 = {"name": "llm2", "base": "http://b/v1", "key": "k2", "gen": "gen-b", "judge": "judge-b"}


def resp(status, text="", content="{}"):
    r = mock.Mock()
    r.status_code, r.ok, r.text = status, status < 400, text
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


class RotationTests(unittest.TestCase):
    def setUp(self):
        picker._cooldown.clear()

    def run_with(self, providers, responses, role="gen"):
        calls = []
        # a mocked sleep does not advance the clock, so let it end any cooldown like a real wait would
        fake_sleep = mock.Mock(side_effect=lambda s: picker._cooldown.clear())

        def fake_post(url, **kw):
            calls.append((url, kw["json"]["model"]))
            return responses.pop(0)

        with mock.patch.object(picker.config, "providers", return_value=providers), \
                mock.patch.object(picker.requests, "post", side_effect=fake_post), \
                mock.patch.object(picker.time, "sleep", fake_sleep) as sleep:
            out = picker.ask_llm("hi", role=role)
        return out, calls, sleep

    def test_switches_to_next_provider_on_429(self):
        out, calls, _ = self.run_with([P1, P2], [resp(429, "try again in 40s"), resp(200, content="OK")])
        self.assertEqual(out, "OK")
        self.assertEqual([c[0] for c in calls], ["http://a/v1/chat/completions", "http://b/v1/chat/completions"])
        self.assertGreater(picker._cooldown["llm1"], 0)

    def test_rate_limited_provider_is_skipped_next_time(self):
        picker._cooldown["llm1"] = 9e12
        out, calls, _ = self.run_with([P1, P2], [resp(200, content="B")])
        self.assertEqual(out, "B")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].startswith("http://b"))

    def test_waits_when_all_providers_limited_then_succeeds(self):
        out, calls, sleep = self.run_with([P1], [resp(429, "try again in 5s"), resp(200, content="late")])
        self.assertEqual(out, "late")
        sleep.assert_called()

    def test_out_of_credits_provider_is_skipped_not_fatal(self):
        picker._hard.clear()
        out, calls, _ = self.run_with([P1, P2], [resp(402, "needs more credits"), resp(200, content="from p2")])
        self.assertEqual(out, "from p2")
        self.assertIn("llm1", picker._hard)
        picker._hard.clear()

    def test_every_provider_out_of_credits_fails_fast_with_a_clear_error(self):
        picker._hard.clear()
        with self.assertRaises(RuntimeError) as cm:
            self.run_with([P1], [resp(402, "needs more credits")])
        self.assertIn("key or credits", str(cm.exception))
        picker._hard.clear()

    def test_judge_role_uses_judge_model(self):
        _, calls, _ = self.run_with([P1], [resp(200)], role="judge")
        self.assertEqual(calls[0][1], "judge-a")

    def test_client_error_is_raised_not_swallowed(self):
        with self.assertRaises(RuntimeError):
            self.run_with([P1, P2], [resp(400, "bad model")])

    def test_parse_retry_after(self):
        self.assertAlmostEqual(picker.parse_retry_after("try again in 9.975s"), 9.975)
        self.assertEqual(picker.parse_retry_after("try again in 1m30s"), 90)
        self.assertEqual(picker.parse_retry_after("try again in 2h3m1s"), 7381)
        self.assertEqual(picker.parse_retry_after("nothing"), 30.0)


if __name__ == "__main__":
    unittest.main()
