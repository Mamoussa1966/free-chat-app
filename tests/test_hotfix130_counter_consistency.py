from conversation_persistence_v26 import persistence_audit

class SS(dict):
    pass


def _chat_with_mixed_messages():
    return {
        "conversation_id": "conv-counter",
        "session_id": "sess-counter",
        "conversation_record": {
            "conversation_id": "conv-counter",
            "session_id": "sess-counter",
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "canonical_store_committed": True,
            "messages": [
                {"message_id": "m1", "role": "user", "request_id": "r1"},
                {"message_id": "m2", "role": "user", "request_id": "r2"},
                {"message_id": "a1", "role": "assistant", "request_id": "r1"},
                {"message_id": "a2", "role": "assistant", "request_id": "r2"},
                {"message_id": "s1", "role": "system", "request_id": "r2"},
            ],
            "requests": [
                {"request_id": "r1", "message_id": "m1"},
                {"request_id": "r2", "message_id": "m2"},
            ],
            "rounds": [
                {"round_id": "conv-counter:r1:r1", "request_id": "r1", "message_id": "m1", "round": 1},
                {"round_id": "conv-counter:r2:r2", "request_id": "r2", "message_id": "m2", "round": 2},
            ],
        },
    }


def test_persistence_counts_use_identity_semantics_not_raw_message_list_length():
    chat = _chat_with_mixed_messages()
    audit = persistence_audit(chat, SS())
    assert len(chat["conversation_record"]["messages"]) == 5
    assert audit["persisted_message_count"] == 2
    assert audit["persisted_request_count"] == 2
    assert audit["persisted_round_count"] == 2
    assert audit["canonical_counter_source"] == "CANONICAL_IDENTITY_RECORDS"
    assert audit["counter_semantics_consistent"] is True


def test_unloaded_canonical_store_fails_closed():
    chat = {"conversation_id": "conv-missing", "session_id": "sess-missing"}
    audit = persistence_audit(chat, SS())
    assert audit["canonical_store_loaded"] == "NOT_PROVEN"
    assert audit["persisted_message_count"] == "NOT_PROVEN"
    assert audit["persisted_request_count"] == "NOT_PROVEN"
    assert audit["persisted_round_count"] == "NOT_PROVEN"
    assert audit["counter_semantics_consistent"] == "NOT_PROVEN"
