from conversation_store import canonical_create_lifecycle, load_canonical_snapshot, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_v25_runtime import authoritative_audit
from conversation_persistence_v26 import persistence_audit


class SS(dict):
    pass


def _chat():
    return {
        "conversation_id": "conv-150",
        "session_id": "sess-150",
        "messages": [],
        "conversation_record": {
            "conversation_id": "conv-150",
            "session_id": "sess-150",
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "messages": [], "requests": [], "rounds": [],
        },
    }


def _turn(chat, ss, n):
    mid, rid = f"m{n}", f"req{n}"
    canonical_create_lifecycle(
        chat,
        {"message_id": mid, "conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "role": "user", "request_id": rid, "created_at": f"2026-09-25T00:00:0{n}Z"},
        {"request_id": rid, "message_id": mid, "conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "state": "COMPLETED", "created_at": f"2026-09-25T00:00:0{n}Z"},
        {"round_id": f"{chat['conversation_id']}:{rid}:r{n}", "request_id": rid, "message_id": mid, "conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "round": n, "round_identity_contract": "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1", "status": "COMPLETED", "created_at": f"2026-09-25T00:00:0{n}Z"},
        ss,
    )


def test_hotfix150_turn1_rerun_turn2_reload_rebuild_proves_exact_binding():
    ss = SS()
    chat = _chat()
    _turn(chat, ss, 1)

    # Streamlit rerun: current object is narrowed to Turn 1 only.
    chat["conversation_record"] = {
        "conversation_id": chat["conversation_id"], "session_id": chat["session_id"],
        "messages": [chat["conversation_record"]["messages"][-1]],
        "requests": [chat["conversation_record"]["requests"][-1]],
        "rounds": [chat["conversation_record"]["rounds"][-1]],
    }
    from conversation_store import prepare_historical_runtime
    prepare_historical_runtime(chat, ss)
    _turn(chat, ss, 2)

    # Second rerun: narrow again, then restore from the same canonical transport.
    chat["conversation_record"] = {
        "conversation_id": chat["conversation_id"], "session_id": chat["session_id"],
        "messages": [chat["conversation_record"]["messages"][-1]],
        "requests": [chat["conversation_record"]["requests"][-1]],
        "rounds": [chat["conversation_record"]["rounds"][-1]],
    }
    assert load_canonical_snapshot(chat, ss) is not None
    hydrate_canonical_record(chat, ss)
    rebuild_runtime_indexes_from_canonical(chat, ss)
    audit = authoritative_audit(chat, ss)
    persisted = persistence_audit(chat, ss)

    assert audit["canonical_counter_source"] == "CANONICAL_IDENTITY_RECORDS"
    assert audit["canonical_message_count"] == 2
    assert audit["canonical_request_count"] == 2
    assert audit["canonical_round_count"] == 2
    assert audit["message_1_request_mapping"] is True
    assert audit["message_2_request_mapping"] is True
    assert audit["request_1_round_1_mapping"] is True
    assert audit["request_2_round_2_mapping"] is True
    assert audit["request_2_round_1_mapping"] is False
    assert audit["canonical_round_ordinals"] == [1, 2]
    assert audit["canonical_round_sequence_base"] == 1
    assert audit["canonical_round_sequence_proven"] is True
    assert audit["round_id_ordinal_consistent"] is True
    assert audit["agent_prose_used_as_identity"] == "NO"
    assert audit["agent_prose_used_as_counter"] == "NO"
    assert persisted["persisted_message_count"] == 2
    assert persisted["persisted_request_count"] == 2
    assert persisted["persisted_round_count"] == 2


def test_hotfix150_preserves_the_observed_inversion_as_not_proven():
    ss = SS()
    chat = _chat()
    _turn(chat, ss, 1)
    _turn(chat, ss, 2)

    # Exact regression fixture: valid Message→Request pairs, but Request/Round
    # identity is inverted. This fixture is intentionally NOT normalized.
    rounds = chat["conversation_record"]["rounds"]
    rounds[0]["request_id"], rounds[1]["request_id"] = rounds[1]["request_id"], rounds[0]["request_id"]
    rounds[0]["message_id"], rounds[1]["message_id"] = rounds[1]["message_id"], rounds[0]["message_id"]
    # Mutate the persisted canonical transport itself to reproduce the observed
    # production inversion. Do not call commit_canonical_record here because its
    # monotonic merge intentionally preserves the last known-good identity.
    bucket = ss["v26_3_canonical_conversation_store"][chat["conversation_id"]]
    bucket["record"]["rounds"] = rounds
    from conversation_store import canonical_history_hash
    bucket["history_hash"] = canonical_history_hash(bucket["record"])

    audit = authoritative_audit(chat, ss)
    assert audit["request_1_round_1_mapping"] is False
    assert audit["request_2_round_2_mapping"] is False
    assert audit["request_2_round_1_mapping"] is True
    assert audit["canonical_round_sequence_proven"] is False
    assert audit["overall_authoritative_status"] == "NOT_PROVEN"
