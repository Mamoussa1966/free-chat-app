from __future__ import annotations

import pytest

from supabase_streamlit_auth import (
    _browser_storage_response_received,
    _normalize_refresh_token,
)


@pytest.mark.parametrize(
    "value",
    [
        "opaque-refresh-token_123",
        "AAECAwQ.eyJ0eXBlIjoicmVmcmVzaCJ9.signature",
    ],
)
def test_valid_refresh_token_values_are_preserved(value):
    assert _normalize_refresh_token(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " token",
        "token ",
        "token with spaces",
        "token\\nvalue",
        "token\\x00value",
        "x" * 4097,
        123,
    ],
)
def test_invalid_refresh_token_values_are_rejected(value):
    assert _normalize_refresh_token(value) is None


def test_browser_storage_result_must_match_expected_action():
    assert _browser_storage_response_received(
        {"action": "read", "value": "", "error": False}, "read"
    )
    assert not _browser_storage_response_received(
        {"action": "delete", "value": "", "error": False}, "read"
    )
    assert not _browser_storage_response_received("stale value", "read")
    assert not _browser_storage_response_received(
        {"action": "read", "value": ""}, "read"
    )
