from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def test_hotfix156_has_exactly_one_adjacent_four_action_bar():
    source = MAIN.read_text(encoding="utf-8")
    assert source.count('st.columns([1.15, 1.15, 1.15, 1.15])') == 1
    assert source.count('Run full V23 platform audit') >= 1
    assert 'v23_platform_audit_actionbar' in source
    assert 'Copy Full V23 Audit Report' in source
    assert 'v23_full_audit_download_151_3' in source
    # The legacy standalone Run button must not remain.
    assert 'key="v23_platform_audit")' not in source


def test_copy_serializes_complete_payload_directly_not_visible_report():
    source = MAIN.read_text(encoding="utf-8")
    assert 'copy_payload = json.dumps(audit_export, ensure_ascii=False, indent=2, sort_keys=True, default=str)' in source
    assert 'navigator.clipboard.writeText(payload)' in source
    assert 'ta.value = payload' in source
    assert 'st.code(audit_export_text, language="json")' in source
    # Copy must not be derived from the visible st.code text.
    assert 'copy_payload = json.dumps(audit_export_text' not in source


def test_download_uses_same_exact_export_text():
    source = MAIN.read_text(encoding="utf-8")
    block = source[source.index('with action_download:'):source.index('st.caption("HOTFIX151.3')]
    assert 'data=audit_export_text if report else ""' in block
    assert 'file_name="V23_FULL_PLATFORM_AUDIT.json"' in block
    assert 'mime="application/json"' in block
