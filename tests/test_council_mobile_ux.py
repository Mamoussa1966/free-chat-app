from __future__ import annotations

from pathlib import Path

import main


def test_empty_mobile_composer_is_not_submittable():
    state = main._composer_submission_state("")
    assert state["can_submit"] is False
    assert state["character_count"] == 0
    assert state["remaining_characters"] == main.MAX_PROMPT_CHARS
    assert state["over_limit"] is False


def test_mobile_composer_accepts_text_or_attachments():
    assert main._composer_submission_state("  hello  ")["can_submit"] is True
    assert main._composer_submission_state("", direct_files=[object()])["can_submit"] is True
    assert main._composer_submission_state("", folder_files=[object()])["can_submit"] is True


def test_mobile_composer_accepts_a_voice_submission_from_the_active_room():
    state = main._composer_submission_state(
        "",
        voice_submission=("transcript", b"audio", "audio/wav", "fingerprint"),
        active_chat_id="chat-1",
    )
    assert state["can_submit"] is True


def test_pending_voice_is_available_only_to_its_own_active_conversation():
    pending = {"chat_id": "chat-1", "audio_bytes": b"audio"}

    active = main._composer_submission_state(
        "", pending_voice=pending, active_chat_id="chat-1"
    )
    other = main._composer_submission_state(
        "", pending_voice=pending, active_chat_id="chat-2"
    )

    assert active["can_submit"] is True
    assert active["pending_voice_ready"] is True
    assert other["can_submit"] is False
    assert other["pending_voice_ready"] is False


def test_mobile_composer_disables_over_limit_text():
    state = main._composer_submission_state("x" * (main.MAX_PROMPT_CHARS + 1))
    assert state["can_submit"] is False
    assert state["over_limit"] is True
    assert state["remaining_characters"] == 0


def test_mobile_composer_allows_exact_maximum_character_count():
    state = main._composer_submission_state("x" * main.MAX_PROMPT_CHARS)
    assert state["can_submit"] is True
    assert state["over_limit"] is False
    assert state["remaining_characters"] == 0


def test_production_composer_exposes_count_and_gates_the_send_button():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "_composer_submission_state(" in source
    assert "disabled=not composer_state[\"can_submit\"]" in source
    assert "عدد الأحرف:" in source
    assert "تجاوزت الرسالة الحد المسموح" in source


def test_default_conversation_view_collapses_heavy_technical_audits():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert 'with st.expander("🧭 HOTFIX118 — Authoritative Historical Conversation Audit", expanded=False):' in source
    assert 'with st.expander("🔐 V23 Security / Context / Platform Audit", expanded=False):' in source


def test_council_header_explains_which_free_api_plans_are_eligible():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "Gemini / Cloudflare Workers AI بعد تأكيد الخطة المجانية" in source
    assert "cloudflare_block = provider_zero_cost_policy_block_reason(cloudflare_seat)" in source


def test_privacy_notice_warns_against_secrets_and_sensitive_content():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "لا ترسل كلمات مرور أو مفاتيح API أو بيانات شديدة الحساسية" in source
    assert "قد تُستخدم البيانات لتحسين منتجات Google" in source
