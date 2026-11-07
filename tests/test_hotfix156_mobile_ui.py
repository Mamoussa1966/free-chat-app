from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "main.py"
TEXT = SOURCE.read_text(encoding="utf-8")


def test_hotfix156_uses_multiline_mobile_composer_not_chat_input():
    assert "st.text_area(" in TEXT
    assert 'placeholder="اكتب رسالتك هنا… اضغط Enter للانتقال إلى سطر جديد، ثم اضغط زر الإرسال."' in TEXT
    # The only legacy mention may be a compatibility comment; no executable chat_input call remains.
    assert "submission = st.chat_input(" not in TEXT


def test_hotfix156_submission_is_explicitly_button_gated_and_readiness_gated():
    send_start = TEXT.index("send_clicked = st.button(")
    send_end = TEXT.index("\n\n    prompt = ", send_start)
    send_block = TEXT[send_start:send_end]
    assert '"📨 إرسال إلى المجلس"' in send_block
    assert "disabled=not composer_state[\"can_submit\"]" in send_block
    assert "elif send_clicked:" in TEXT
    assert "_text_prompt_for_submission(typed_prompt, send_clicked)" in TEXT


def test_hotfix156_section_actions_have_copy_print_download():
    assert "def _render_section_actions(" in TEXT
    assert "📋 نسخ" in TEXT
    assert "🖨️ طباعة" in TEXT
    assert '"⬇️ Download"' in TEXT
    assert TEXT.count("_render_section_actions(") >= 10


def test_hotfix156_v23_action_bar_has_four_actions_in_one_block():
    assert "action_run, action_copy, action_print, action_download" in TEXT
    assert "v23_full_audit_print_disabled_156" in TEXT
    assert "v23_full_audit_download_151_3" in TEXT
    start = TEXT.index('with st.expander("🔐 V23 Security / Context / Platform Audit", expanded=False):')
    block = TEXT[start:TEXT.index('if __name__ == "__main__":')]
    assert "Run full V23 platform audit" in block
    assert "Copy Full V23 Audit Report" in block
    assert "Print" in block
    assert "Download Full V23 Audit JSON" in block


def test_hotfix156_preserves_free_only_provider_contract():
    assert "لا Local Engine ولا Paid fallback" in TEXT
    assert "Gemini Free Tier وCloudflare Workers AI Free" in TEXT
    assert "provider_zero_cost_policy_block_reason" in TEXT
    assert "capture_credentials" in TEXT
    assert "capture_model_candidates" in TEXT


def test_hotfix156_idle_composer_does_not_hide_following_sections():
    marker = "elif send_clicked:"
    start = TEXT.index(marker)
    tail = TEXT[start:TEXT.index("if attachments is None:", start)]
    assert "return" not in tail
    assert 'prompt = ""' in tail
    assert "attachments = []" in tail
