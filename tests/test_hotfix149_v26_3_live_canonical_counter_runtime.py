from conversation_store import canonical_create_lifecycle, load_canonical_snapshot, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_persistence_v26 import persistence_audit
from conversation_v25_runtime import authoritative_audit


def _chat(cid="conv-149", sid="sess-149"):
    return {
        "conversation_id": cid,
        "session_id": sid,
        # Deliberately noisy UI/runtime projection: this must NEVER become the
        # authoritative counter source.
        "messages": [],
        "conversation_record": {
            "conversation_id": cid,
            "session_id": sid,
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "messages": [],
            "requests": [],
            "rounds": [],
        },
    }


def _lifecycle(chat, state, n):
    mid, rid = f"m{n}", f"r{n}"
    rowid = f"{chat['conversation_id']}:{rid}:{n}"
    return canonical_create_lifecycle(
        chat,
        {
            "message_id": mid,
            "conversation_id": chat["conversation_id"],
            "session_id": chat["session_id"],
            "role": "user",
            "content": f"turn {n}",
            "request_id": rid,
            "created_at": f"2026-09-24T00:00:0{n}Z",
        },
        {
            "request_id": rid,
            "conversation_id": chat["conversation_id"],
            "session_id": chat["session_id"],
            "message_id": mid,
            "state": "COMMITTED",
            "created_at": f"2026-09-24T00:00:0{n}Z",
        },
        {
            "round_id": rowid,
            "conversation_id": chat["conversation_id"],
            "session_id": chat["session_id"],
            "message_id": mid,
            "request_id": rid,
            "round": n,
            "status": "COMMITTED",
            "round_identity_contract": "V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1",
            "created_at": f"2026-09-24T00:00:0{n}Z",
        },
        state,
    )


def test_live_runtime_counter_comes_only_from_canonical_identity_records():
    state = {}
    chat = _chat()

    _lifecycle(chat, state, 1)
    _lifecycle(chat, state, 2)

    # Add provider/assistant/system artifacts to the canonical store itself.
    rec = chat["conversation_record"]
    rec["messages"].extend([
        {"message_id": "a1", "role": "assistant", "request_id": "r1"},
        {"message_id": "a2", "role": "assistant", "request_id": "r2"},
        {"message_id": "s1", "role": "system", "request_id": "r2"},
    ])
    # Make the UI-facing projection intentionally misleading/noisy.
    chat["messages"] = [
        {"role": "user", "content": "turn 1"},
        {"role": "assistant", "content": "provider 1"},
        {"role": "assistant", "content": "synthesis 1"},
        {"role": "user", "content": "turn 2"},
        {"role": "assistant", "content": "provider 2"},
        {"role": "system", "content": "system artifact"},
        {"role": "assistant", "content": "synthesis 2"},
    ]

    # Commit the exact canonical record after adding non-user artifacts.
    from conversation_store import commit_canonical_record
    commit_canonical_record(chat, state)

    audit = authoritative_audit(chat, state)
    persisted = persistence_audit(chat, state)

    assert audit["canonical_counter_source"] == "CANONICAL_IDENTITY_RECORDS"
    assert audit["canonical_message_count"] == 2
    assert audit["canonical_request_count"] == 2
    assert audit["canonical_round_count"] == 2
    assert persisted["canonical_counter_source"] == "CANONICAL_IDENTITY_RECORDS"
    assert persisted["persisted_message_count"] == 2
    assert persisted["persisted_request_count"] == 2
    assert persisted["persisted_round_count"] == 2
    assert len(chat["messages"]) == 7


def test_live_runtime_counter_survives_hydration_and_rerun_projection():
    state = {}
    chat = _chat("conv-149b", "sess-149b")
    _lifecycle(chat, state, 1)
    _lifecycle(chat, state, 2)

    # Simulate a Streamlit rerun that narrows the in-memory/UI object to one turn.
    narrowed = _chat("conv-149b", "sess-149b")
    narrowed["conversation_record"]["messages"] = [
        {"message_id": "m2", "role": "user", "request_id": "r2"}
    ]
    narrowed["conversation_record"]["requests"] = [
        {"request_id": "r2", "message_id": "m2"}
    ]
    narrowed["conversation_record"]["rounds"] = [
        {"round_id": "conv-149b:r2:2", "request_id": "r2", "message_id": "m2", "round": 2}
    ]
    narrowed["messages"] = [{"role": "user", "content": "turn 2"}]

    snapshot = load_canonical_snapshot(narrowed, state)
    assert snapshot is not None
    hydrate_canonical_record(narrowed, state)
    rebuild_runtime_indexes_from_canonical(narrowed, state)

    audit = authoritative_audit(narrowed, state)
    persisted = persistence_audit(narrowed, state)

    assert audit["canonical_transport_loaded"] is True
    assert audit["canonical_message_count"] == 2
    assert audit["canonical_request_count"] == 2
    assert audit["canonical_round_count"] == 2
    assert persisted["persisted_message_count"] == 2
    assert persisted["persisted_request_count"] == 2
    assert persisted["persisted_round_count"] == 2
    assert audit["agent_prose_used_as_counter"] == "NO"
