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
    assert "json" not in post.call_args.kwargs  # exactly one serialized body reaches the transport
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

    manifest = json.loads(Path("HOTFIX164.30_RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["release"] == "HOTFIX164.30"
    assert providers.CURRENT_HOTFIX_RELEASE_VERSION.startswith(manifest["release"] + " ")
    import main
    assert main.DISPLAY_VERSION == providers.CURRENT_HOTFIX_RELEASE_VERSION
    assert main.PLATFORM_RELEASE_VERSION == providers.PLATFORM_RELEASE_VERSION
    assert providers.VERSION == Path("VERSION.txt").read_text(encoding="utf-8").strip()


def test_hotfix16428_transport_sends_only_the_attested_prepared_body():
    import hashlib
    import json
    response = type("Response", (), {"status_code": 200, "text": "{}", "headers": {}, "json": lambda self: {}})()
    payload = {"contents": [{"parts": [{"text": "sanitized target prompt"}]}]}
    with patch("providers.requests.post", return_value=response) as post:
        assert _post("https://example.invalid/v1beta/models/gemini:generateContent", {"Content-Type": "application/json"}, payload, 5) == {}
    kwargs = post.call_args.kwargs
    body = kwargs["data"]
    attestation = providers._take_runtime_payload_attestation()
    assert isinstance(body, bytes)
    assert "json" not in kwargs
    assert hashlib.sha256(body).hexdigest() == attestation["payload_sha256"]
    assert body == attestation["payload_json"].encode("utf-8")
    assert json.loads(body) == payload

def test_hotfix16430_failed_gemini_transport_exports_attempt_metadata_without_passing():
    import hashlib
    import json
    import main

    seat = next(s for s in providers.get_seats() if s.key == "gemini")
    request_id = "hotfix16430-failed-gemini-r1"
    endpoint = "https://example.invalid/v1beta/models/gemini-3.6-flash:generateContent"
    payload_json = json.dumps(
        {"contents": [{"role": "user", "parts": [{"text": "safe diagnostic"}]}]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload_bytes = payload_json.encode("utf-8")

    def fail_after_http_503(*args, **kwargs):
        providers._RUNTIME_ATTESTATION_LOCAL.value = {
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "payload_bytes": len(payload_bytes),
            "endpoint_sha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
            "payload_json": payload_json,
            "transport_boundary": "requests.PreparedRequest.body",
            "prepared_request_verified": True,
            "transport_attempt_status": "HTTP_ERROR",
            "transport_response_received": True,
            "transport_http_status_code": 503,
            "transport_error_class": "transient_provider_error",
        }
        raise ProviderError(
            "HTTP 503: temporary service issue",
            503,
            "transient_provider_error",
        )

    with patch("providers.call_official", side_effect=fail_after_http_503):
        result = providers.call_seat(
            seat,
            "safe diagnostic",
            "",
            1,
            False,
            "test-credential",
            attachments=[],
            model_candidates=("gemini-3.6-flash",),
            request_id=request_id,
        )

    assert result["status"] == "FAILED"
    attestation = result["_runtime_payload_attestation"]
    assert attestation["payload_sha256"] == hashlib.sha256(payload_bytes).hexdigest()
    assert attestation["payload_bytes"] == len(payload_bytes)
    assert attestation["executed_model"] == "gemini-3.6-flash"
    assert attestation["transport_attempt_status"] == "HTTP_ERROR"
    assert attestation["transport_http_status_code"] == 503
    assert attestation["transport_error_class"] == "transient_provider_error"
    assert attestation["transport_response_attached"] is False
    assert attestation["request_id"] == request_id
    assert attestation["round_no"] == 1
    assert attestation["seat_key"] == "gemini"
    assert attestation["seat_slot"] == 2

    bridge = main.SharedContextBridge(
        request_id=request_id,
        round_no=1,
        strict_live_source=True,
    )
    bridge._runtime_bridge_evidence["canonical_round_id"] = f"conversation:{request_id}:r1"
    bridge.record_provider_input(seat, "safe diagnostic")
    bridge.record_runtime_payload_attestation(seat, attestation)
    checked = bridge._runtime_payload_attestations[2]
    assert checked["request_identity_binding_status"] == "PASS"
    assert checked["round_identity_binding_status"] == "PASS"
    assert checked["target_identity_binding_status"] == "PASS"
    assert checked["transport_response_binding_status"] == "NOT_PROVEN"
    assert checked["canonical_round_binding_status"] == "PASS"
    assert checked["integrity_valid"] is False

    runtime_record = bridge.runtime_evidence_record()
    exported = main._hotfix16429_export_runtime_http_attestation(
        runtime_record, request_id, "1"
    )
    assert exported["payload_sha256"] == hashlib.sha256(payload_bytes).hexdigest()
    assert exported["payload_bytes"] == len(payload_bytes)
    assert exported["transport_attempt_status"] == "HTTP_ERROR"
    assert exported["transport_http_status_code"] == 503
    assert exported["transport_error_class"] == "transient_provider_error"
    assert exported["http_payload_attested"] == "NO"
    assert exported["payload_hash_integrity"] == "FAIL"
    assert exported["response_binding_status"] == "NOT_PROVEN"
    serialized = json.dumps(runtime_record, sort_keys=True)
    assert payload_json not in serialized
    assert "safe diagnostic" not in serialized

