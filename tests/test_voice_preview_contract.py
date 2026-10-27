"""Fast source-level contract for voice-preview controls; no browser required."""
from pathlib import Path


def test_production_voice_preview_controls_are_ordered():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    room_start = source.index("def _render_user_room(")
    audio_input = source.index(
        'st.audio_input("🎙️ تسجيل رسالة صوتية"', room_start
    )
    preview_player = source.index("st.audio(audio_bytes, format=mime)", audio_input)
    discard_button = source.index('"🗑️ حذف التسجيل قبل الإرسال"', preview_player)
    send_button = source.index(
        'st.button("🎤 إرسال الصوت للمجلس"', discard_button
    )

    assert audio_input < preview_player < discard_button < send_button
    voice_section = source[audio_input:send_button]
    assert "st.session_state.voice_nonce = int(" in voice_section
    assert "st.session_state.last_voice_transcription = {}" in voice_section
    assert 'st.session_state.last_voice_error = ""' in voice_section
    assert "st.rerun()" in voice_section
