from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_native_supabase_auth_probe_is_test_project_only_and_browser_side():
    source = (ROOT / "supabase_native_auth_probe.py").read_text(encoding="utf-8")
    page = (ROOT / "pages" / "12_Supabase_Native_Auth_Denial_Probe.py").read_text(encoding="utf-8")
    page11 = (ROOT / "pages" / "11_Clerk_Auth_Pilot.py").read_text(encoding="utf-8")

    assert "TEST_SUPABASE_URL" in source
    assert "TEST_SUPABASE_PUBLISHABLE_KEY" in source
    assert "pidcepvwsezdrlhxqksg.supabase.co" not in source
    assert "free-chat-app-qmqyxzh2oe2n3qwcvqvpdh.streamlit.app" not in source
    assert "/auth/v1/token?grant_type=password" in source
    assert "/auth/v1/user" in source
    assert "/rest/v1/clerk_auth_pilot_records?select=record_id&limit=10" in source
    assert "/auth/v1/logout?scope=local" in source
    assert '<button id="run-probe" type="button">' in source
    assert 'runButton.addEventListener("click", runProbe)' in source
    assert 'emailInput.addEventListener("input", updateReadyState)' in source
    assert 'passwordInput.addEventListener("input", updateReadyState)' in source
    assert "SUPABASE-NATIVE-AUTH-DENIAL-PROBE-20261112" in source
    assert "render_supabase_native_auth_denial_probe" in page
    assert "render_supabase_native_auth_denial_probe" in page11


def test_native_supabase_auth_probe_never_persists_or_returns_password_or_token():
    source = (ROOT / "supabase_native_auth_probe.py").read_text(encoding="utf-8")

    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "Streamlit.setComponentValue" not in source
    assert "parent.postMessage" not in source
    assert "service_role" not in source.lower()
    assert "SUPABASE_SECRET_KEY" not in source
    assert "st.text_input" not in source
    assert "st.text_area" not in source
    assert "passwordInput.value = \"\"" in source
    assert "accessToken = \"\"" in source


def test_native_supabase_auth_probe_requires_a_zero_row_rls_result_for_read_pass():
    source = (ROOT / "supabase_native_auth_probe.py").read_text(encoding="utf-8")

    assert "readResponse.status === 200" in source
    assert "Array.isArray(rows) && rows.length === 0" in source
    assert "readResponse.status === 401 || readResponse.status === 403" in source
    assert "FAIL: رمز Supabase Auth قرأ" in source
    assert "لا تُحسب PASS" in source
