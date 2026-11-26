import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))
import picker  # noqa: E402

P1 = {"name": "llm1", "base": "http://a/v1", "key": "k1", "gen": "g", "judge": "j"}


def resp(content):
    r = mock.Mock()
    r.status_code, r.ok, r.text = 200, True, ""
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


class EmptyReplyTests(unittest.TestCase):
    def setUp(self):
        picker._cooldown.clear()

    def test_empty_reply_is_retried(self):
        seq = [resp(None), resp("   "), resp("{\"ok\": 1}")]
        with mock.patch.object(picker.config, "providers", return_value=[P1]), \
                mock.patch.object(picker.requests, "post", side_effect=lambda *a, **k: seq.pop(0)), \
                mock.patch.object(picker.time, "sleep"):
            self.assertEqual(picker.ask_llm("hi", role="judge"), "{\"ok\": 1}")

    def test_gives_up_with_a_clear_error_when_always_empty(self):
        with mock.patch.object(picker.config, "providers", return_value=[P1]), \
                mock.patch.object(picker.requests, "post", side_effect=lambda *a, **k: resp(None)), \
                mock.patch.object(picker.time, "sleep"):
            with self.assertRaises(RuntimeError) as cm:
                picker.ask_llm("hi")
            self.assertIn("empty reply", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
