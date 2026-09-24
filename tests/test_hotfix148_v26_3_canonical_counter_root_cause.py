from conversation_v25_runtime import authoritative_audit


def test_v26_3_authoritative_audit_uses_user_message_identity_semantics():
    chat = {
        "conversation_id": "conv-148",
        "session_id": "sess-148",
        "messages": [
            {"role": "user", "content": "turn 1"},
            {"role": "assistant", "content": "provider result"},
            {"role": "assistant", "content": "synthesis"},
        ],
        "conversation_record": {
            "conversation_id": "conv-148",
            "session_id": "sess-148",
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
                {"round_id": "conv-148:r1:r1", "request_id": "r1", "message_id": "m1", "round": 1, "conversation_id": "conv-148", "session_id": "sess-148", "round_identity_contract": "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
                {"round_id": "conv-148:r2:r2", "request_id": "r2", "message_id": "m2", "round": 2, "conversation_id": "conv-148", "session_id": "sess-148", "round_identity_contract": "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
            ],
        },
        "request_records": [
            {"request_id": "r1", "message_id": "m1", "results": []},
            {"request_id": "r2", "message_id": "m2", "results": []},
        ],
    }
    state = {"v26_3_canonical_conversation_store": {"conv-148": {"record": chat["conversation_record"], "revision": 1}}}
    audit = authoritative_audit(chat, state)
    assert audit["canonical_message_count"] == 2
    assert audit["canonical_request_count"] == 2
    assert audit["canonical_round_count"] == 2


def test_v26_3_authoritative_audit_never_counts_non_user_artifacts_as_messages():
    chat = {
        "conversation_id": "conv-148b",
        "session_id": "sess-148b",
        "messages": [],
        "conversation_record": {
            "conversation_id": "conv-148b",
            "session_id": "sess-148b",
            "canonical_store_committed": True,
            "messages": [
                {"message_id": "a1", "role": "assistant"},
                {"message_id": "s1", "role": "system"},
            ],
            "requests": [],
            "rounds": [],
        },
        "request_records": [],
    }
    state = {"v26_3_canonical_conversation_store": {"conv-148b": {"record": chat["conversation_record"], "revision": 1}}}
    audit = authoritative_audit(chat, state)
    assert audit["canonical_message_count"] == 0
