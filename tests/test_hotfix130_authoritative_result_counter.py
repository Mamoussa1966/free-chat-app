from main import _authoritative_ui_projection, _format_authoritative_counter_summary


def test_authoritative_ui_projection_is_non_authoritative():
    projection = _authoritative_ui_projection({
        "messages": [
            {"role": "user", "message_id": "m1"},
            {"role": "assistant", "message_id": "a1"},
        ]
    }, [{"status": "SUCCESS"}])
    assert projection["message_count"] == 2
    assert projection["result_rows"] == 1
    assert projection["message_count_authoritative"] is False
    assert projection["authoritative_counter_source"] == "V26_3_CANONICAL_CONVERSATION_STORE"


def test_authoritative_counter_summary_uses_canonical_fields():
    summary = _format_authoritative_counter_summary({
        "canonical_message_count": 2,
        "canonical_request_count": 2,
        "canonical_round_count": 2,
        "counter_semantics_consistent": True,
    })
    assert "canonical_message_count=2" in summary
    assert "canonical_request_count=2" in summary
    assert "canonical_round_count=2" in summary
    assert "counter_semantics_consistent=True" in summary
