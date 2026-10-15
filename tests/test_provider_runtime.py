import providers
import unittest
from unittest.mock import patch
import requests
from providers import ProviderError, _post, _prompt

class ProviderRuntimeTests(unittest.TestCase):
    def test_prompt_markers(self):
        text = _prompt("Hello", "CTX", 1)
        self.assertEqual(text.count("CURRENT USER REQUEST:"), 1)
        self.assertIn("UNTRUSTED SHARED CONTEXT", text)
    def test_billing_not_retried(self):
        response = type("Response", (), {"status_code": 429, "text": '{"error":"credit balance exhausted"}', "headers": {}, "json": lambda self: {}})()
        with patch("providers.requests.post", return_value=response) as post:
            with self.assertRaises(ProviderError): _post("https://example.invalid", {}, {}, 5)
        self.assertEqual(post.call_count, 1)
    def test_network_retries_once(self):
        response = type("Response", (), {"status_code": 200, "text": "{}", "headers": {}, "json": lambda self: {}})()
        with patch("providers.requests.post", side_effect=[requests.Timeout(), response]) as post:
            self.assertEqual(_post("https://example.invalid", {}, {}, 5, retries=1), {})
        self.assertEqual(post.call_count, 2)

if __name__ == "__main__": unittest.main()


def test_404_model_classification_wins_over_quota_wording():
    assert providers._classify(404, "model not found; quota information unavailable") == "model_not_found_or_invalid"


def test_429_distinguishes_rate_limit_from_explicit_quota():
    assert providers._classify(429, "too many requests") == "http_429_rate_limit_or_quota"
    assert providers._classify(429, "quota exceeded") == "billing_or_quota"


def test_hotfix16413_attests_exact_prepared_http_body_bytes():
    import hashlib
    import json
    response = type("Response", (), {"status_code": 200, "text": "{}", "headers": {}, "json": lambda self: {}})()
    payload = {"input": "safe café", "model": "configured-free-model"}
    with patch("providers.requests.post", return_value=response) as post:
        assert _post("https://example.invalid/v1/messages", {"Content-Type": "application/json"}, payload, 5) == {}
    sent_body = post.call_args.kwargs["data"]
    assert isinstance(sent_body, bytes)
    assert post.call_args.kwargs["json"] == payload  # backward-compatible adapter kwarg; non-empty data is the transmitted body
    assert json.loads(sent_body.decode("utf-8")) == payload
    attestation = providers._take_runtime_payload_attestation()
    assert attestation["prepared_request_verified"] is True
    assert attestation["transport_boundary"] == "requests.PreparedRequest.body"
    assert attestation["payload_sha256"] == hashlib.sha256(sent_body).hexdigest()
    assert attestation["payload_bytes"] == len(sent_body)
    assert attestation["payload_json"].encode("utf-8") == sent_body


def test_current_runtime_release_label_matches_release_manifest():
    import json
    from pathlib import Path

    manifest = json.loads(Path("HOTFIX164.25_RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["release"] == "HOTFIX164.25"
    assert providers.CURRENT_HOTFIX_RELEASE_VERSION.startswith(manifest["release"] + " ")
    import main
    assert main.DISPLAY_VERSION == providers.CURRENT_HOTFIX_RELEASE_VERSION
    assert main.PLATFORM_RELEASE_VERSION == providers.PLATFORM_RELEASE_VERSION
    assert providers.VERSION == Path("VERSION.txt").read_text(encoding="utf-8").strip()
