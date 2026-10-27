"""Regression contract: a voice transcript is not a complete send without its audio blob."""
from pathlib import Path


def test_production_uploads_original_audio_before_provider_request_dispatch():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    upload_at = source.index("voice_storage.upload(voice_storage_path, voice_audio, voice_mime)")
    lifecycle_at = source.index("canonical_upsert_request(chat, record0, st.session_state)")
    dispatch_at = source.index("results = _run_council(", lifecycle_at)
    assert upload_at < lifecycle_at < dispatch_at
    assert "لم تُرسل الرسالة إلى المجلس" in source
    assert "لم نعتمد التفريغ النصي وحده كنجاح" in source


def test_voice_message_links_original_audio_and_restores_it_after_session_reload():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert 'voice_message_metadata["voice_storage_path"] = voice_storage_path' in source
    assert "blob = voice_storage.download(voice_storage_path)" in source
    assert "voice_storage.delete([voice_storage_path])" in source
    assert "voice_storage_path" in source[source.index("def _supabase_presentation_state"):source.index("def _supabase_persist_completed_chat")]
