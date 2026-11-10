"""Regression tests for independent Streamlit conversation sessions."""

from copy import deepcopy

from main import _merge_owner_history_with_session_chats, _new_chat


def test_new_chat_allocates_independent_conversation_and_session_ids():
    first = _new_chat()
    second = _new_chat()

    assert first["id"] != second["id"]
    assert first["conversation_id"] != second["conversation_id"]
    assert first["session_id"] != second["session_id"]
    assert first["messages"] == []
    assert second["messages"] == []


def test_new_streamlit_session_keeps_its_fresh_chat_active_after_history_load():
    historical_messages = [
        {"role": "user", "id": f"user-{index}", "content": f"question {index}"}
        if index % 2 == 0
        else {"role": "assistant", "id": f"assistant-{index}", "content": f"answer {index}"}
        for index in range(33)
    ]
    historical = {
        "id": "historical-conversation",
        "conversation_id": "historical-conversation",
        "title": "Historical 33-message conversation",
        "messages": historical_messages,
        "request_ids": ["historical-request-1"],
        "request_records": [{"request_id": "historical-request-1", "state": "COMPLETED"}],
    }
    original_historical = deepcopy(historical)
    session_draft = _new_chat()

    merged, active_id = _merge_owner_history_with_session_chats(
        [historical],
        [session_draft],
        session_draft["id"],
    )

    assert active_id == session_draft["id"]
    assert merged[0] is session_draft
    assert historical in merged
    assert historical == original_historical
    assert len(historical["messages"]) == 33
    assert historical["request_ids"] == ["historical-request-1"]


def test_explicitly_selected_saved_conversation_remains_active_during_history_reload():
    historical = {
        "id": "historical-conversation",
        "conversation_id": "historical-conversation",
        "messages": [{"role": "user", "id": "u1", "content": "saved"}],
    }
    session_draft = _new_chat()

    merged, active_id = _merge_owner_history_with_session_chats(
        [historical],
        [session_draft],
        "historical-conversation",
    )

    assert active_id == "historical-conversation"
    assert historical in merged
    assert session_draft in merged


def test_history_load_preserves_all_local_unsaved_conversations_and_deduplicates_remote_rows():
    historical = {
        "id": "history-1",
        "conversation_id": "history-1",
        "messages": [{"role": "user", "id": "u1"}],
    }
    local_draft = _new_chat()
    local_unsaved_chat = _new_chat()
    duplicate_local = {
        "id": "history-1",
        "conversation_id": "history-1",
        "messages": [{"role": "user", "id": "u1"}],
    }

    merged, active_id = _merge_owner_history_with_session_chats(
        [historical],
        [local_draft, local_unsaved_chat, duplicate_local],
        local_draft["id"],
    )

    assert active_id == local_draft["id"]
    assert merged == [local_draft, local_unsaved_chat, historical]
    assert sum(item["id"] == "history-1" for item in merged) == 1


def test_empty_owner_history_does_not_replace_current_session_chat():
    local_draft = _new_chat()

    merged, active_id = _merge_owner_history_with_session_chats(
        [],
        [local_draft],
        local_draft["id"],
    )

    assert merged == [local_draft]
    assert active_id == local_draft["id"]
