""""Regression tests for handing a captured voice preview into the council request path."""
from pathlib import Path

from main import _pending_voice_recording_for_send


ROOT = Path(__file__).resolve().parents[1]


def test_pending_voice_is_not_submitted_without_explicit_send():
    pending = {
        "chat_id": "chat-a",
        "audio_bytes": b"real-audio-bytes",
        "mime": "audio/webm",
        "fingerprint": "fingerprint-a",
    }

    assert _pending_voice_recording_for_send(pending, "chat-a", False) is None
    assert _pending_voice_recording_for_send(pending, "chat-b", True) is None
    assert _pending_voice_recording_for_send({}, "chat-a", True) is None


def test_pending_voice_for_active_chat_preserves_audio_and_identity():
    pending = {
        "chat_id": "chat-a",
        "audio_bytes": bytearray(b"captured-audio"),
        "mime": "audio/webm;codecs=opus",
        "fingerprint": "fingerprint-a",
    }

    result = _pending_voice_recording_for_send(pending, "chat-a", True)

    assert result == {
        "chat_id": "chat-a",
        "audio_bytes": b"captured-audio",
        "mime": "audio/webm;codecs=opus",
        "fingerprint": "fingerprint-a",
    }


def test_pending_voice_resolver_rejects_invalid_audio_and_generates_missing_fingerprint():
    assert _pending_voice_recording_for_send(
        {"chat_id": "chat-a", "audio_bytes": "not-bytes"}, "chat-a", True
    ) is None
    assert _pending_voice_recording_for_send(
        {"chat_id": "chat-a", "audio_bytes": b""}, "chat-a", True
    ) is None

    result = _pending_voice_recording_for_send(
        {"chat_id": "chat-a", "audio_bytes": b"captured-audio", "mime": ""},
        "chat-a",
        True,
    )
    assert result is not None
    assert result["audio_bytes"] == b"captured-audio"
    assert result["mime"] == "audio/wav"
    assert result["fingerprint"]


def test_production_preview_and_global_send_are_connected_to_request_path():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    preview_start = source.index("def _render_user_room(")
    audio_input = source.index('st.audio_input("🎙️ تسجيل رسالة صوتية"', preview_start)
    cache = source.index('st.session_state["pending_voice_recording"] = {', audio_input)
    preview = source.index("st.audio(audio_bytes, format=mime)", cache)
    discard = source.index('"🗑️ حذف التسجيل قبل الإرسال"', preview)
    room_send = source.index('st.button("🎤 إرسال الصوت للمجلس"', discard)

    resolver_start = source.index("def _pending_voice_recording_for_send(")
    composer_start = source.index('typed_prompt = st.text_area(', resolver_start)
    global_send = source.index('send_clicked = st.button("📨 إرسال إلى المجلس"', composer_start)
    handoff = source.index('pending_voice = _pending_voice_recording_for_send(', global_send)
    transcription = source.index("transcription = transcribe_audio_gemini(", handoff)
    voice_submission = source.index("voice_submission = (transcript_text, audio_bytes, mime, fingerprint)", transcription)
    request_gate = source.index("if prompt or attachments:", voice_submission)
    request_dispatch = source.index(
        "_run_council(prompt, chat, rounds, credentials, attachments, model_candidates, user_message_id, request_id, bridge_controls)",
        request_gate,
    )

    assert audio_input < cache < preview < discard < room_send
    assert global_send < handoff < transcription < voice_submission < request_gate < request_dispatch
    assert 'st.session_state["pending_voice_recording"] = {}' in source
    assert 'st.session_state["pending_voice_recording"] = {}' in source[source.index('def _cleanup_voice_media_after_chat_delete'):]
