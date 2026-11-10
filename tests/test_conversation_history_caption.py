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

from main import _conversation_timeline_messages


def test_timeline_preserves_all_messages_in_original_order():
    messages = [
        {"role": "user", "id": "u1", "content": "first"},
        {"role": "assistant", "id": "a1", "seat_key": "gemini", "content": "ROUND_OK"},
        {"role": "assistant", "id": "a2", "seat_key": "cloudflare_workers_ai", "content": "ROUND_OK"},
        {"role": "user", "id": "u2", "content": "second"},
    ]
    timeline = _conversation_timeline_messages({"messages": messages})
    assert timeline == messages
    assert [message["seat_key"] for message in timeline if message["role"] == "assistant"] == [
        "gemini",
        "cloudflare_workers_ai",
    ]


def test_timeline_ignores_malformed_entries_without_reordering_valid_messages():
    messages = [
        {"role": "user", "id": "u1", "content": "first"},
        None,
        {"role": "system", "id": "s1", "content": "internal"},
        {"role": "assistant", "id": "a1", "content": "answer"},
    ]
    assert _conversation_timeline_messages({"messages": messages}) == [
        messages[0],
        messages[3],
    ]


def test_timeline_handles_missing_or_invalid_message_projection():
    assert _conversation_timeline_messages({}) == []
    assert _conversation_timeline_messages({"messages": None}) == []
    assert _conversation_timeline_messages({"messages": "invalid"}) == []
