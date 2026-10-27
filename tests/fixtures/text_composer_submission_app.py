"""Isolated Streamlit AppTest harness for the production text-composer handoff.

This exercises real Streamlit widget reruns but never calls a provider API.
"""
import streamlit as st

from main import _text_prompt_for_submission

if "request_cycle_payloads" not in st.session_state:
    st.session_state["request_cycle_payloads"] = []

typed_prompt = st.text_area(
    "💬 رسالة المجلس",
    placeholder="اكتب رسالتك هنا… اضغط Enter للانتقال إلى سطر جديد، ثم اضغط زر الإرسال.",
    key="council_message_input_0",
)
send_clicked = st.button(
    "📨 إرسال إلى المجلس",
    type="primary",
    key="send_message_0",
)

# This is the same resolver call used by run_app() in production.
prompt = _text_prompt_for_submission(typed_prompt, send_clicked)
if prompt:
    # Capture precisely what the real request path receives, without dispatching
    # any network/provider request from an automated regression test.
    st.session_state["request_cycle_payloads"].append(prompt)

st.caption(f"Captured request submissions: {len(st.session_state['request_cycle_payloads'])}")
