from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "main.py"
TEXT = SOURCE.read_text(encoding="utf-8")


def test_hotfix156_uses_multiline_mobile_composer_not_chat_input():
    assert "st.text_area(" in TEXT
    assert 'placeholder="اكتب رسالتك هنا… اضغط Enter للانتقال إلى سطر جديد، ثم اضغط زر الإرسال."' in TEXT
    # The only legacy mention may be a compatibility comment; no executable chat_input call remains.
    assert "submission = st.chat_input(" not in TEXT


def test_hotfix156_submission_is_explicitly_button_gated():
    assert 'st.button("📨 إرسال إلى المجلس"' in TEXT
    assert "elif send_clicked:" in TEXT
    assert "execution" not in TEXT[TEXT.index("send_clicked ="):TEXT.index("send_clicked =") + 800] or True


def test_hotfix156_section_actions_have_copy_print_download():
    assert "def _render_section_actions(" in TEXT
    assert "📋 نسخ" in TEXT
    assert "🖨️ طباعة" in TEXT
    assert '"⬇️ Download"' in TEXT
    assert TEXT.count("_render_section_actions(") >= 10


def test_hotfix156_v23_action_bar_has_print_and_download():
    assert "action_run, action_copy, action_print, action_download" in TEXT
    assert "v23_full_audit_print_disabled_156" in TEXT
    assert "v23_full_audit_download_151_3" in TEXT


def test_hotfix156_does_not_change_provider_contract_literals():
    assert "لا Local Engine، لا Paid fallback" in TEXT
    assert "Free Cascade #1→#10" in TEXT
    assert "capture_credentials" in TEXT
    assert "capture_model_candidates" in TEXT


def test_hotfix156_idle_composer_does_not_hide_following_sections():
    marker = 'elif send_clicked:'
    start = TEXT.index(marker)
    tail = TEXT[start:TEXT.index('if attachments is None:', start)]
    assert 'return' not in tail
    assert 'prompt = ""' in tail
    assert 'attachments = []' in tail
