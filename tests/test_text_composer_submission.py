"""Regression tests for the Streamlit text-composer -> request prompt handoff."""
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "fixtures" / "text_composer_submission_app.py"


def test_textarea_value_reaches_request_payload_only_after_send_click():
    message = "اختبار إرسال نص QA-20261027: يجب أن يصل هذا النص كما هو إلى دورة الطلب."

    app = AppTest.from_file(str(HARNESS), default_timeout=15).run()
    assert not app.exception
    assert len(app.text_area) == 1
    assert app.text_area[0].label == "💬 رسالة المجلس"
    assert len(app.button) == 1
    assert app.button[0].label == "📨 إرسال إلى المجلس"
    assert app.session_state["request_cycle_payloads"] == []

    # An edit causes a Streamlit rerun, but must not dispatch by itself.
    app.text_area[0].set_value(message).run()
    assert not app.exception
    assert app.session_state["request_cycle_payloads"] == []

    # Clicking the explicit send button must pass the current text to the
    # request-cycle boundary once, preserving the content exactly.
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["request_cycle_payloads"] == [message]

    # A plain subsequent rerun must not replay the one-run button event.
    app.run()
    assert not app.exception
    assert app.session_state["request_cycle_payloads"] == [message]


def test_production_run_app_wires_exact_text_widget_and_send_event_to_request_path():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    run_app_start = source.index("def run_app() -> None:")
    composer_start = source.index('typed_prompt = st.text_area(', run_app_start)
    send_button = source.index('send_clicked = st.button("📨 إرسال إلى المجلس"', composer_start)
    resolver = source.index(
        "prompt = _text_prompt_for_submission(typed_prompt, send_clicked)",
        send_button,
    )
    submission_gate = source.index("if prompt or attachments:", resolver)
    request_dispatch = source.index(
        "_run_council(prompt, chat, rounds, credentials, attachments, model_candidates, user_message_id, request_id, bridge_controls)",
        submission_gate,
    )

    assert composer_start < send_button < resolver < submission_gate < request_dispatch
    assert 'key=input_key' in source[composer_start:send_button]
    assert 'key=f"send_message_{st.session_state.input_nonce}"' in source[send_button:resolver]
