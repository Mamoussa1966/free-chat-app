from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def test_hotfix151_2_has_adjacent_three_action_bar():
    source = MAIN.read_text(encoding="utf-8")
    assert 'st.columns([1.25, 1.25, 1.25])' in source
    assert 'v23_platform_audit_actionbar' in source
    assert 'Copy Full V23 Audit Report' in source
    assert 'v23_full_audit_download_151_2' in source


def test_copy_uses_complete_export_payload_not_visible_code_widget():
    source = MAIN.read_text(encoding="utf-8")
    assert 'copy_payload = json.dumps(audit_export_text, ensure_ascii=False)' in source
    assert 'navigator.clipboard.writeText(payload)' in source
    assert 'ta.value = payload' in source
    assert 'st.code(audit_export_text, language="json")' in source


def test_download_uses_same_exact_export_text():
    source = MAIN.read_text(encoding="utf-8")
    block = source[source.index('with action_download:'):source.index('st.caption("HOTFIX151.2')]
    assert 'data=audit_export_text' in block
    assert 'file_name="V23_FULL_PLATFORM_AUDIT.json"' in block
    assert 'mime="application/json"' in block
