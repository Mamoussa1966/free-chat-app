import unittest
from unittest.mock import patch
from providers import transcribe_audio_gemini

class VoiceTests(unittest.TestCase):
    def test_voice_requires_credential(self):
        result = transcribe_audio_gemini(b"audio", "audio/wav", None)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("not_configured", result["error"])
    def test_empty_audio_is_rejected(self):
        result = transcribe_audio_gemini(b"", "audio/wav", "dummy")
        self.assertIn("empty_audio", result["error"])
    def test_voice_model_must_be_explicit(self):
        def setting(names):
            return "true" if "GEMINI_API_ZERO_COST_CONFIRMED" in tuple(names) else None
        with patch("providers._setting", side_effect=setting):
            result = transcribe_audio_gemini(b"audio", "audio/wav", "dummy")
        self.assertIn("transcriber_model_not_configured", result["error"])

if __name__ == "__main__": unittest.main()
