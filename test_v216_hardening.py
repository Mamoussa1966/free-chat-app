import ast
import unittest


class V22HardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("main.py", "r", encoding="utf-8") as handle:
            cls.main_source = handle.read()
        with open("providers.py", "r", encoding="utf-8") as handle:
            cls.provider_source = handle.read()

    def test_no_local_engine_path_in_main(self):
        tree = ast.parse(self.main_source)
        source = self.main_source
        self.assertNotIn('st.session_state.local_fallback = True', source)
        self.assertNotIn('status"] == "LOCAL"', source)
        self.assertNotIn('from local_engine import', source)
        self.assertIsNotNone(tree)

    def test_free_cascade_is_explicit(self):
        self.assertIn("Free API Cascade", self.main_source)
        self.assertIn("Free #1", self.main_source)
        self.assertIn("حتى 10", self.main_source)
        self.assertIn("*_FREE_MODELS", self.main_source)

    def test_voice_and_typed_text_are_combined(self):
        self.assertIn("typed_prompt", self.main_source)
        self.assertIn("[تفريغ الرسالة الصوتية]", self.main_source)

    def test_voice_replay_protection_is_per_chat(self):
        self.assertIn('voice_fingerprints.get(chat["id"], set())', self.main_source)
        self.assertIn('fingerprints.setdefault(chat["id"], set())', self.main_source)

    def test_provider_attachment_cap_exists(self):
        self.assertIn("MAX_PROVIDER_ATTACHMENT_BYTES", self.provider_source)
        self.assertIn("def _provider_attachments", self.provider_source)

    def test_provider_cap_is_ten(self):
        self.assertIn("MAX_MODELS_PER_SEAT = 10", self.provider_source)


if __name__ == "__main__":
    unittest.main()
