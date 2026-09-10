import unittest
from unittest.mock import patch
from providers import transcribe_audio_gemini

class VoiceResilienceTests(unittest.TestCase):
    def test_invalid_audio_type(self):
        result = transcribe_audio_gemini("not-bytes", "audio/wav", "dummy")
        self.assertIn("invalid_audio", result["error"])
    def test_invalid_audio_mime(self):
        result = transcribe_audio_gemini(b"audio", "text/plain", "dummy")
        self.assertIn("invalid_audio_mime", result["error"])
    def test_explicit_model_is_used(self):
        fake = {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
        with patch("providers._post", return_value=fake) as post:
            result = transcribe_audio_gemini(b"audio", "audio/webm; codecs=opus", "dummy", ("free-transcriber",))
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["model"], "free-transcriber")
        self.assertEqual(post.call_args.args[2]["contents"][0]["parts"][1]["inlineData"]["mimeType"], "audio/webm")

if __name__ == "__main__": unittest.main()
