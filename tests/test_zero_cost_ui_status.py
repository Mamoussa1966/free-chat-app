from pathlib import Path


def test_zero_cost_blocked_provider_is_not_marked_ready_in_sidebar():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    start = source.index('st.subheader("🔌 الاعتمادات والنماذج")')
    end = source.index('st.caption(f"Model config fingerprint:', start)
    block = source[start:end]

    assert "block_reason = provider_zero_cost_policy_block_reason(seat)" in block
    assert 'status_icon = "⛔" if block_reason else ("🟢" if models else "⚪")' in block
    assert 'st.markdown(f"{status_icon} **{seat.name}**' in block
    assert "credentials.get(seat.key) else" not in block
