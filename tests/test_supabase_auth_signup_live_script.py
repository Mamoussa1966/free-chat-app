from __future__ import annotations

from scripts.test_supabase_auth_signup_live import preflight


def _set_valid_environment(monkeypatch):
    values = {
        "SUPABASE_URL": "https://example-test.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_ci_test_key",
        "SUPABASE_TEST_USER_A_EMAIL": "account-a@example.test",
        "SUPABASE_TEST_USER_A_PASSWORD": "A-Long-Test-Password-123",
        "SUPABASE_TEST_USER_B_EMAIL": "account-b@example.test",
        "SUPABASE_TEST_USER_B_PASSWORD": "B-Long-Test-Password-456",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_signup_preflight_validates_and_preserves_password_whitespace(monkeypatch):
    values = _set_valid_environment(monkeypatch)
    values["SUPABASE_TEST_USER_A_PASSWORD"] = "  A-Long-Test-Password-123  "
    monkeypatch.setenv(
        "SUPABASE_TEST_USER_A_PASSWORD",
        values["SUPABASE_TEST_USER_A_PASSWORD"],
    )

    config = preflight()

    assert config is not None
    project_url, publishable_key, users = config
    assert project_url == values["SUPABASE_URL"]
    assert publishable_key == values["SUPABASE_PUBLISHABLE_KEY"]
    assert users[0] == (
        "A",
        values["SUPABASE_TEST_USER_A_EMAIL"],
        values["SUPABASE_TEST_USER_A_PASSWORD"],
    )
    assert users[1][1] == values["SUPABASE_TEST_USER_B_EMAIL"]


def test_signup_preflight_reports_invalid_second_password_without_echoing_values(
    monkeypatch, capsys
):
    values = _set_valid_environment(monkeypatch)
    values["SUPABASE_TEST_USER_B_PASSWORD"] = "tiny"
    monkeypatch.setenv("SUPABASE_TEST_USER_B_PASSWORD", "tiny")

    config = preflight()

    output = capsys.readouterr().out
    assert config is None
    assert "LIVE_AUTH_SIGNUP=FAIL" in output
    assert "SUPABASE_TEST_USER_B_PASSWORD_INVALID" in output
    assert "8 و1024" in output
    assert "account-a@example.test" not in output
    assert values["SUPABASE_TEST_USER_A_PASSWORD"] not in output
    assert "tiny" not in output
