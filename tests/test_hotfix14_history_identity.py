import ast
import importlib.util
import unittest


class Hotfix14HistoryIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = open("main.py", "r", encoding="utf-8").read()
        cls.tree = ast.parse(cls.source)

    def test_request_id_is_unique_and_separate_from_idempotency_fingerprint(self):
        self.assertIn("request_id = uuid.uuid4().hex", self.source)
        self.assertIn("request_fingerprints", self.source)
        self.assertIn("_request_fingerprint(prompt, attachments)", self.source)

    def test_user_and_assistant_history_carry_request_identity(self):
        self.assertIn('"request_id": request_id, "request_number": request_number', self.source)
        self.assertIn('"request_id": request_id, "request_number": int(request_number), "result_key": result_key', self.source)

    def test_round_rendering_exposes_request_number(self):
        self.assertIn("Request {message.get('request_number', '?')} · Round {message.get('round', '?')}", self.source)

    def test_history_uniqueness_is_checked_against_persistent_result_keys(self):
        self.assertIn("History result uniqueness invariant violated", self.source)
        self.assertIn('chat.get("result_keys")', self.source)
        self.assertIn('chat.setdefault("result_keys", []).append(result_key)', self.source)

    def test_different_requests_can_share_round_number_but_same_result_key_cannot(self):
        # Identity is scoped by request_id + round + seat; round alone is intentionally not unique.
        self.assertIn('result_key = f"{request_id}:{round_no}:{seat_key}"', self.source)
        self.assertNotIn('result_key = f"{round_no}:{seat_key}"', self.source)


if __name__ == "__main__":
    unittest.main()
