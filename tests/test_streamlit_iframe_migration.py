from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_app_uses_supported_streamlit_iframe_api_for_javascript_html():
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "from streamlit.components.v1 import html as components_html" not in source
    assert "components_html(" not in source
    assert source.count("st.iframe(") == 5


def test_javascript_behaviors_remain_wired_after_iframe_migration():
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    # Copy/print buttons and timed diagnostic dismissal still require a
    # JavaScript-capable iframe. Keep these trusted, application-authored
    # snippets in st.iframe rather than st.html's sanitized inline context.
    assert "navigator.clipboard.writeText" in source
    assert "window.print()" in source
    assert "setTimeout(()=>{{ el.remove(); }}" in source
    assert "speechSynthesis" in source


def test_bidirectional_supabase_v1_component_bridge_is_not_replaced():
    source = (ROOT / "supabase_streamlit_auth.py").read_text(encoding="utf-8")

    # The recovery listener and encrypted browser-session bridge use the
    # bidirectional component protocol; this migration only replaces static
    # HTML+JavaScript rendering calls in main.py.
    assert "declare_component(" in source
    assert "declare_component_v2(" in source
    assert "_RECOVERY_CALLBACK_COMPONENT" in source
    assert "_BROWSER_SESSION_COMPONENT" in source
