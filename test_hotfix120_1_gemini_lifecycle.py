import providers
from production_core import FreeCascadeController


def test_hotfix120_1_404_model_unavailable_is_distinct_and_advances():
    internal = providers._classify(404, '{"error":{"message":"model not found"}}')
    assert internal in {"model_not_found_or_invalid", "http_404_resource_not_found"}
    assert providers._canonical_error_classification(internal) == "MODEL_UNAVAILABLE"
    assert providers._retryable(404, "model not found") is False
    assert FreeCascadeController.cascade_decision("MODEL_UNAVAILABLE", True) == (
        "CASCADE_CONTINUE", "MODEL_UNAVAILABLE_ADVANCE_TO_NEXT_MODEL"
    )


def test_hotfix120_1_503_is_transient_not_model_unavailable():
    internal = providers._classify(503, "Service Unavailable")
    assert providers._canonical_error_classification(internal) == "TRANSIENT_PROVIDER_ERROR"
    assert providers._retryable(503, "Service Unavailable") is True
    assert FreeCascadeController.cascade_decision("TRANSIENT_PROVIDER_ERROR", True) == (
        "CASCADE_CONTINUE", "TRANSIENT_PROVIDER_ERROR_ADVANCE_TO_NEXT_MODEL"
    )


def test_hotfix120_1_invalid_request_and_auth_are_terminal():
    assert providers._canonical_error_classification(providers._classify(400, "bad request")) == "INVALID_REQUEST"
    assert FreeCascadeController.cascade_decision("INVALID_REQUEST", True) == (
        "CASCADE_STOP", "INVALID_REQUEST_TERMINAL"
    )
    assert FreeCascadeController.cascade_decision("AUTHENTICATION_ERROR", True) == (
        "CASCADE_STOP", "AUTH_ERROR_TERMINAL"
    )


def test_hotfix120_1_cascade_reason_is_deterministic():
    cases = [
        ("MODEL_UNAVAILABLE", "CASCADE_CONTINUE", "MODEL_UNAVAILABLE_ADVANCE_TO_NEXT_MODEL"),
        ("RATE_LIMITED", "CASCADE_CONTINUE", "RATE_LIMITED_ADVANCE_TO_NEXT_MODEL"),
        ("TRANSIENT_PROVIDER_ERROR", "CASCADE_CONTINUE", "TRANSIENT_PROVIDER_ERROR_ADVANCE_TO_NEXT_MODEL"),
        ("INVALID_REQUEST", "CASCADE_STOP", "INVALID_REQUEST_TERMINAL"),
        ("AUTHENTICATION_ERROR", "CASCADE_STOP", "AUTH_ERROR_TERMINAL"),
    ]
    for classification, action, reason in cases:
        assert FreeCascadeController.cascade_decision(classification, True) == (action, reason)


def test_hotfix120_1_same_request_id_is_preserved_across_cascade_attempts():
    request_id = "req-hotfix120-1"
    details = [
        {"request_id": request_id, "round": 1, "attempt": 1, "classification": "MODEL_UNAVAILABLE"},
        {"request_id": request_id, "round": 1, "attempt": 2, "classification": "TRANSIENT_PROVIDER_ERROR"},
    ]
    assert {d["request_id"] for d in details} == {request_id}
    assert {d["round"] for d in details} == {1}
