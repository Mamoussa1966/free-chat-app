"""Isolated browser-test harness for Streamlit's real st.audio_input widget.

This is intentionally not the production entrypoint. It has no authentication,
provider keys, persistence, or network integration with the AI Council.
"""
import streamlit as st

st.set_page_config(page_title="Voice microphone browser smoke test", layout="centered")
st.title("اختبار الميكروفون الافتراضي")
st.caption("واجهة اختبار محلية فقط؛ لا ترسل أي صوت إلى المجلس ولا تستخدم حسابًا حقيقيًا.")

if "voice_nonce" not in st.session_state:
    st.session_state.voice_nonce = 0
if "test_only_submissions" not in st.session_state:
    st.session_state.test_only_submissions = 0

st.markdown("**🎙️ صوت داخل الغرفة**")
audio = st.audio_input(
    "🎙️ تسجيل رسالة صوتية",
    sample_rate=16000,
    key=f"voice_input_{st.session_state.voice_nonce}",
)

if audio:
    audio_bytes = bytes(audio.getvalue())
    mime = str(getattr(audio, "type", None) or "audio/wav")
    st.audio(audio_bytes, format=mime)
    st.write(f"Captured audio bytes: {len(audio_bytes)}")
    if st.button(
        "🗑️ حذف التسجيل قبل الإرسال",
        key=f"discard_voice_preview_{st.session_state.voice_nonce}",
        use_container_width=True,
    ):
        st.session_state.voice_nonce = int(st.session_state.voice_nonce) + 1
        st.rerun()

    if st.button(
        "🎤 إرسال الصوت للمجلس",
        key=f"send_voice_{st.session_state.voice_nonce}",
        type="primary",
        use_container_width=True,
    ):
        # Deliberately a local counter, never an API call.
        st.session_state.test_only_submissions += 1
        st.success("TEST ONLY: local submit handler invoked; no audio was sent.")
else:
    st.caption("No pending audio preview.")

st.caption(f"Test-only submission count: {st.session_state.test_only_submissions}")
