import unittest
from unittest.mock import patch

from providers import transcribe_audio_gemini


class V215ResilienceTests(unittest.TestCase):

    def test_invalid_audio_type_is_rejected(self):

        result = transcribe_audio_gemini(
            "not-bytes",
            "audio/wav",
            "dummy",
        )

        self.assertEqual(
            result["status"],
            "FAILED",
        )

        self.assertIn(
            "invalid_audio",
            result["error"],
        )

    def test_transcriber_uses_dedicated_model_by_default(self):

        fake = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "hello"
                            }
                        ]
                    }
                }
            ]
        }

        with patch(
            "providers._post",
            return_value=fake,
        ) as post:

            result = transcribe_audio_gemini(
                b"audio",
                "audio/wav",
                "dummy",
            )

        self.assertEqual(
            result["status"],
            "SUCCESS",
        )

        self.assertEqual(
            result["model"],
            "gemini-3.5-transcribe",
        )

        self.assertIn(
            "gemini-3.5-transcribe:generateContent",
            post.call_args.args[0],
        )


if __name__ == "__main__":
    unittest.main()
