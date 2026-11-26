import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import picker  # noqa: E402


class PickerTests(unittest.TestCase):
    def test_dedupe_removes_history_and_duplicates(self):
        items = [{"title": "Roman Concrete!"}, {"title": "roman concrete"},
                 {"title": "Used Topic"}, {"title": "Fresh One"}]
        out = picker.dedupe(items, ["used topic"])
        self.assertEqual([i["title"] for i in out], ["Roman Concrete!", "Fresh One"])

    def test_parse_idea_ok_and_list_wrapper(self):
        idea = {k: "x" for k in picker.REQUIRED}
        self.assertEqual(picker.parse_idea(json.dumps(idea))["topic"], "x")
        self.assertEqual(picker.parse_idea(json.dumps([idea]))["topic"], "x")

    def test_parse_idea_missing_field(self):
        with self.assertRaises(ValueError):
            picker.parse_idea(json.dumps({"topic": "x"}))

    def test_ask_llm_parses_openai_style_response(self):
        from unittest import mock
        fake = mock.Mock(status_code=200, ok=True)
        fake.json.return_value = {"choices": [{"message": {"content": "{\"a\": 1}"}}]}
        only = [{"name": "llm1", "base": "http://x/v1", "key": "k", "gen": "g", "judge": "j"}]
        with mock.patch.object(picker.config, "providers", return_value=only), \
                mock.patch.object(picker.requests, "post", return_value=fake) as post:
            self.assertEqual(picker.ask_llm("hi"), "{\"a\": 1}")
        url = post.call_args.args[0]
        self.assertTrue(url.endswith("/chat/completions"))

    def test_ask_llm_requires_key_for_remote(self):
        from unittest import mock
        no_key = [{"name": "llm1", "base": "https://remote.example/v1", "key": "", "gen": "g", "judge": "j"}]
        with mock.patch.object(picker.config, "providers", return_value=no_key):
            with self.assertRaises(RuntimeError):
                picker.ask_llm("hi")

    def test_pick_raises_when_nothing_fresh(self):
        with self.assertRaises(RuntimeError):
            picker.pick([{"title": "a"}], ["a"])


if __name__ == "__main__":
    unittest.main()
