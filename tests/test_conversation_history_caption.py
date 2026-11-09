from main import _conversation_history_caption


def test_empty_local_chat_is_labeled_as_an_unsent_draft():
    assert _conversation_history_caption({
        "messages": [],
        "created_at": "2026-11-09T21:12:00Z",
        "title": "محادثة جديدة",
    }) == "مسودة جديدة • لم تُرسل أي رسالة بعد"


def test_chat_with_messages_keeps_count_and_created_timestamp():
    assert _conversation_history_caption({
        "messages": [{"role": "user"}, {"role": "assistant"}, {"role": "user"}],
        "created_at": "2026-10-29 07:09 UTC",
    }) == "3 رسالة • 2026-10-29 07:09 UTC"


def test_invalid_messages_projection_fails_closed_to_draft_label():
    assert _conversation_history_caption({
        "messages": None,
        "created_at": "2026-11-09T21:12:00Z",
    }) == "مسودة جديدة • لم تُرسل أي رسالة بعد"
