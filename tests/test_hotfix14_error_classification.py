import main
import providers


def test_error_classification_canonical_categories():
    assert providers._canonical_error_classification("model_not_found_or_invalid") == "MODEL_UNAVAILABLE"
    assert providers._canonical_error_classification("billing_or_quota") == "QUOTA_EXCEEDED"
    assert providers._canonical_error_classification("http_429_rate_limit_or_quota") == "RATE_LIMITED"
    assert providers._canonical_error_classification("http_401_authentication_failed") == "AUTHENTICATION_ERROR"
    assert providers._canonical_error_classification("provider_server") == "API_ERROR"
    assert providers._canonical_error_classification("network") == "NETWORK_ERROR"
    assert providers._canonical_error_classification("timeout") == "TIMEOUT"
    assert providers._canonical_error_classification("future_error_class") == "UNKNOWN"


def test_history_attempt_summary_excludes_raw_provider_error():
    raw = "HTTP 429; class=billing_or_quota; secret=DO_NOT_STORE; provider JSON"
    summaries = main._history_attempt_summaries([{
        "attempt": 1,
        "model": "gemini-3.8-flash",
        "status_code": 429,
        "classification": "QUOTA_EXCEEDED",
        "error_class": "billing_or_quota",
        "error": raw,
        "retryable": True,
    }])
    assert summaries == [{
        "attempt": 1,
        "model": "gemini-3.8-flash",
        "status_code": 429,
        "classification": "QUOTA_EXCEEDED",
        "retryable": True,
    }]
    assert raw not in str(summaries)


def test_all_public_error_classifications_are_stable():
    cases = [
        (404, "model not found", "MODEL_UNAVAILABLE"),
        (429, "quota exceeded", "QUOTA_EXCEEDED"),
        (429, "too many requests", "RATE_LIMITED"),
        (401, "invalid api key", "AUTHENTICATION_ERROR"),
        (403, "permission denied", "AUTHENTICATION_ERROR"),
        (500, "internal server error", "API_ERROR"),
        (400, "bad request", "API_ERROR"),
    ]
    for status, body, expected in cases:
        internal = providers._classify(status, body)
        assert providers._canonical_error_classification(internal) == expected


def test_history_summary_never_persists_raw_google_payload_or_links():
    raw = (
        'HTTP 429; class=billing_or_quota; https://ai.google.dev/gemini-api/docs/rate-limits; '
        'https://ai.dev/rate-limit; provider JSON details'
    )
    summaries = main._history_attempt_summaries([{
        'attempt': 1,
        'model': 'gemini-3.8-flash',
        'status_code': 429,
        'classification': 'QUOTA_EXCEEDED',
        'error_class': 'billing_or_quota',
        'error': raw,
        'retryable': False,
    }])
    serialized = str(summaries)
    assert 'ai.google.dev' not in serialized
    assert 'ai.dev/rate-limit' not in serialized
    assert 'provider JSON' not in serialized


def test_history_attempt_summary_has_ui_ttl_timestamp_and_no_raw_payload():
    raw = 'HTTP 429; https://ai.google.dev/gemini-api/docs/rate-limits; provider JSON secret=NO'
    summaries = main._history_attempt_summaries([{
        'attempt': 1,
        'model': 'gemini-3.8-flash',
        'status_code': 429,
        'classification': 'QUOTA_EXCEEDED',
        'error_class': 'billing_or_quota',
        'error': raw,
        'retryable': True,
        '_display_created_at': 1234567890.0,
    }])
    assert summaries[0]['created_at_epoch'] == 1234567890.0
    assert summaries[0]['classification'] == 'QUOTA_EXCEEDED'
    assert raw not in str(summaries)
    assert 'ai.google.dev' not in str(summaries)


def test_error_display_ttl_is_sixty_seconds():
    assert main.ERROR_DISPLAY_TTL_SECONDS == 60


def test_attempt_diagnostic_expires_after_sixty_seconds():
    created = 1000.0
    assert main._attempt_display_remaining({"created_at_epoch": created}, now=1059.999) > 0
    assert main._attempt_display_remaining({"created_at_epoch": created}, now=1060.0) == 0
    assert main._attempt_display_remaining({"created_at_epoch": created}, now=1061.0) == 0


def test_attempt_diagnostic_missing_timestamp_is_not_rendered():
    assert main._attempt_display_remaining({"classification": "QUOTA_EXCEEDED"}, now=1000.0) == 0
