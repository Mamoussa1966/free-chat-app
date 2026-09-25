from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def test_v23_audit_has_one_visible_heading_and_one_action_bar():
    source = MAIN.read_text(encoding="utf-8")
    assert source.count('st.expander("🔐 V23 Security / Context / Platform Audit", expanded=True)') == 1
    assert source.count('st.subheader("🔐 V23 Security / Context / Platform Audit")') == 0
    assert source.count('st.columns([1.25, 1.25, 1.25])') == 1


def test_three_action_labels_remain_in_same_block():
    source = MAIN.read_text(encoding="utf-8")
    start = source.index('with st.expander("🔐 V23 Security / Context / Platform Audit", expanded=True):')
    end = source.index('if __name__ == "__main__":')
    block = source[start:end]
    assert 'Run full V23 platform audit' in block
    assert 'Copy Full V23 Audit Report' in block
    assert 'Download Full V23 Audit JSON' in block
