from pathlib import Path

import main
import providers
from providers import SEATS, call_seat
DEEPSEEK = next(seat for seat in SEATS if seat.key == "deepseek")


def _response(status, text, payload=None):
    class Response:
        status_code = status
        def __init__(self):
            self.text = text
            self.headers = {}
        def json(self):
            return payload if payload is not None else {}
    return Response()


def test_hotfix80_deepseek_flash_alias_is_success():
    response = _response(200, '{"model":"deepseek-flash","choices":[{"message":{"content":"OK"}}]}',
                         {"model":"deepseek-flash","choices":[{"message":{"content":"OK"}}]})
    from unittest.mock import patch
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "hello", "", 1, False, "TEST_KEY", [],
                           ("deepseek-v4-flash",), request_id="hotfix80-flash")
    assert post.call_count == 1
    assert result["status"] == "SUCCESS"
    assert result["executed_model"] == "deepseek-v4-flash"
    assert result["provider_reported_model"] == "deepseek-flash"


def test_hotfix80_deepseek_0731_alias_is_success():
    response = _response(200, '{"model":"deepseek-v4-flash-0731","choices":[{"message":{"content":"OK"}}]}',
                         {"model":"deepseek-v4-flash-0731","choices":[{"message":{"content":"OK"}}]})
    from unittest.mock import patch
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "hello", "", 1, False, "TEST_KEY", [],
                           ("deepseek-v4-flash",), request_id="hotfix80-0731")
    assert post.call_count == 1
    assert result["status"] == "SUCCESS"
    assert result["provider_reported_model"] == "deepseek-v4-flash-0731"


def test_hotfix80_deepseek_pro_identity_mismatch_remains_fail_closed():
    response = _response(200, '{"model":"deepseek-v4-pro","choices":[{"message":{"content":"WRONG"}}]}',
                         {"model":"deepseek-v4-pro","choices":[{"message":{"content":"WRONG"}}]})
    from unittest.mock import patch
    with patch("providers.requests.post", return_value=response) as post:
        result = call_seat(DEEPSEEK, "hello", "", 1, False, "TEST_KEY", [],
                           ("deepseek-v4-flash", "deepseek-v4-pro"), request_id="hotfix80-mismatch")
    assert post.call_count == 1
    assert result["status"] == "FAILED"
    assert result["attempted_models"] == ["deepseek-v4-flash"]
    assert result["attempt_diagnostics"][0]["error_class"] == "execution_identity_mismatch"


def test_hotfix80_api_error_on_candidate_one_advances_to_candidate_two():
    first = _response(500, '{"error":{"message":"temporary"}}', {"error":{"message":"temporary"}})
    second = _response(200, '{"model":"deepseek-v4-pro","choices":[{"message":{"content":"OK"}}]}',
                        {"model":"deepseek-v4-pro","choices":[{"message":{"content":"OK"}}]})
    from unittest.mock import patch
    with patch("providers.requests.post", side_effect=[first, second]) as post:
        result = call_seat(DEEPSEEK, "hello", "", 1, False, "TEST_KEY", [],
                           ("deepseek-v4-flash", "deepseek-v4-pro"), request_id="hotfix80-cascade")
    assert post.call_count == 2
    assert result["status"] == "SUCCESS"
    assert result["attempted_models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert result["executed_model"] == "deepseek-v4-pro"
    assert result["attempt_diagnostics"][0]["classification"] in {"API_ERROR", "TRANSIENT_PROVIDER_ERROR"}


def test_hotfix80_main_uses_provider_identity_definition_for_result_and_rendering():
    source = Path(main.__file__).read_text()
    assert "provider_reported_model != executed_model" not in source
    assert "_provider_identity_matches" in source
    assert "Provider identity invariant violated" in source
