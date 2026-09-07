import ast
import unittest

from providers import _parse_models, _retry_delay


class V213HardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("main.py", "r", encoding="utf-8") as handle:
            cls.main_source = handle.read()

    def test_current_user_exclusion_is_in_context_builder(self):
        tree = ast.parse(self.main_source)

        fn = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_shared_context"
        )

        source = ast.get_source_segment(
            self.main_source,
            fn,
        ) or ""

        self.assertIn(
            "exclude_message_id",
            source,
        )

        self.assertIn(
            'item.get("id") == exclude_message_id',
            source,
        )

    def test_context_labels_local_and_official_sources(self):
        self.assertIn(
            'source = "OFFICIAL" if item.get("mode") == "official" else "LOCAL"',
            self.main_source,
        )

        self.assertIn(
            "[{source}]",
            self.main_source,
        )

    def test_model_override_is_deduplicated_and_bounded(self):
        raw = "a,b,a,c,d,e"

        self.assertEqual(
            _parse_models(raw),
            ("a", "b", "c", "d"),
        )

    def test_retry_after_is_bounded(self):
        response = type(
            "Response",
            (),
            {
                "headers": {
                    "Retry-After": "999"
                }
            },
        )()

        self.assertEqual(
            _retry_delay(response, 0),
            5.0,
        )


if __name__ == "__main__":
    unittest.main()
