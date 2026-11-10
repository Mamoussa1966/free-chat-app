"""Regression tests for independent Streamlit conversation sessions."""

from copy import deepcopy

from main import _merge_owner_history_with_session_chats, _new_chat, _start_new_chat_session_state


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



def test_new_button_transition_clears_active_transcript_and_keeps_old_history_unchanged():
    historical = _new_chat()
    historical["id"] = "historical-id"
    historical["conversation_id"] = "historical-conversation-id"
    historical["session_id"] = "historical-session-id"
    historical["title"] = "Historical chat"
    historical["messages"] = [
        {"role": "user", "id": "old-user", "content": "old prompt"},
        {"role": "assistant", "id": "old-answer", "content": "old answer"},
    ]
    historical["request_ids"] = ["old-request-fingerprint"]
    old_snapshot = deepcopy(historical)
    state = {
        "chats": [historical],
        "active_chat_id": historical["id"],
        "last_results": [{"seat": "gemini", "content": "old response"}],
        "last_diagnostics": [{"seat": "cloudflare_workers_ai"}],
        "last_synthesis": {"status": "SUCCESS"},
        "last_continuation_audit": {"mode": "READ_ONLY"},
        "last_hotfix141_harness": [{"request_id": "old-request"}],
        "_canonical_round_status_repair": {"conversation_id": historical["conversation_id"]},
        "last_voice_transcription": {"chat_id": historical["id"]},
        "pending_voice_recording": {"chat_id": historical["id"]},
        "last_voice_error": "old error",
        "input_nonce": 4,
        "folder_nonce": 2,
        "voice_nonce": 7,
    }

    new_chat = _start_new_chat_session_state(state)

    assert state["active_chat_id"] == new_chat["id"]
    assert state["chats"][0] is new_chat
    assert historical in state["chats"]
    assert historical == old_snapshot
    assert new_chat["messages"] == []
    assert new_chat["id"] != historical["id"]
    assert new_chat["conversation_id"] != historical["conversation_id"]
    assert new_chat["session_id"] != historical["session_id"]
    assert state["last_results"] == []
    assert state["last_diagnostics"] == []
    assert state["last_synthesis"] == {}
    assert state["last_continuation_audit"] == {}
    assert state["last_hotfix141_harness"] == []
    assert state["_canonical_round_status_repair"] == {}
    assert state["last_voice_transcription"] == {}
    assert state["pending_voice_recording"] == {}
    assert state["last_voice_error"] == ""
    assert state["input_nonce"] == 5
    assert state["folder_nonce"] == 3
    assert state["voice_nonce"] == 8


def test_repeated_new_button_transitions_create_distinct_independent_chats():
    state = {"chats": [], "active_chat_id": ""}
    first = _start_new_chat_session_state(state)
    second = _start_new_chat_session_state(state)

    assert first is not second
    assert first["id"] != second["id"]
    assert first["conversation_id"] != second["conversation_id"]
    assert first["session_id"] != second["session_id"]
    assert second["id"] == state["active_chat_id"]
    assert state["chats"] == [second, first]
    assert first["messages"] == []
    assert second["messages"] == []
