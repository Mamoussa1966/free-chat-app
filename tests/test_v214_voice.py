import unittest

from providers import transcribe_audio_gemini


class V214VoiceTests(unittest.TestCase):
    def test_voice_requires_gemini_credential(self):
        result = transcribe_audio_gemini(
            b"audio",
            "audio/wav",
            None,
            ("gemini-3.8-flash",),
        )

        self.assertEqual(
            result["status"],
            "FAILED",
        )

        self.assertIn(
            "not_configured",
            result["error"],
        )

    def test_empty_audio_is_rejected(self):
        result = transcribe_audio_gemini(
            b"",
            "audio/wav",
            "dummy",
            ("gemini-3.8-flash",),
        )

        self.assertEqual(
            result["status"],
            "FAILED",
        )

        self.assertIn(
            "empty_audio",
            result["error"],
        )


if __name__ == "__main__":
    unittest.main()
