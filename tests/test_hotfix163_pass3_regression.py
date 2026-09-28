import copy

from conversation_store import hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_v25_runtime import ensure_v25_store, reconcile_v26_message_ledger


def _canonical():
    return {
        "id": "p3",
        "conversation_id": "conv-p3",
        "session_id": "sess-p3",
        "conversation_record": {
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "canonical_store_committed": True,
            "conversation_id": "conv-p3",
            "session_id": "sess-p3",
            "messages": [
                {"message_id": "m1", "request_id": "r1", "conversation_id": "conv-p3", "session_id": "sess-p3", "role": "user"},
                {"message_id": "m2", "request_id": "r2", "conversation_id": "conv-p3", "session_id": "sess-p3", "role": "user"},
            ],
            "requests": [
                {"request_id": "r1", "message_id": "m1", "conversation_id": "conv-p3", "session_id": "sess-p3", "canonical_round_base": 1},
                {"request_id": "r2", "message_id": "m2", "conversation_id": "conv-p3", "session_id": "sess-p3", "canonical_round_base": 2},
            ],
            "rounds": [
                {"round_id": "conv-p3:r1:r1", "request_id": "r1", "message_id": "m1", "conversation_id": "conv-p3", "session_id": "sess-p3", "round": 1},
                {"round_id": "conv-p3:r2:r2", "request_id": "r2", "message_id": "m2", "conversation_id": "conv-p3", "session_id": "sess-p3", "round": 2},
            ],
        },
        "request_records": [],
        "messages": [],
        "round_ledger": [],
    }


def test_pass3_hydrate_without_session_state_uses_full_canonical_record():
    chat = _canonical()
    hydrate_canonical_record(chat, None)
    rebuild_runtime_indexes_from_canonical(chat, None)
    assert [x["message_id"] for x in chat["message_ledger"]] == ["m1", "m2"]
    assert [x["request_id"] for x in chat["request_records"]] == ["r1", "r2"]
    assert [x["round_id"] for x in chat["round_ledger"]] == ["conv-p3:r1:r1", "conv-p3:r2:r2"]


def test_pass3_message_relink_is_idempotent_and_does_not_invent_identity():
    chat = {"id": "p3", "conversation_id": "conv-p3", "session_id": "sess-p3", "request_records": [{"request_id": "r1", "state": "COMPLETED"}]}
    ensure_v25_store(chat)
    reconcile_v26_message_ledger(chat)
    assert chat["message_ledger_v26"] == []
    reconcile_v26_message_ledger(chat)
    assert chat["message_ledger_v26"] == []


def test_pass3_conflicting_message_binding_never_overwrites_first_binding():
    chat = {"id": "p3", "conversation_id": "conv-p3", "session_id": "sess-p3", "request_records": [
        {"request_id": "r1", "message_id": "m1", "state": "COMPLETED"},
        {"request_id": "r2", "message_id": "m1", "state": "COMPLETED"},
    ]}
    ensure_v25_store(chat)
    reconcile_v26_message_ledger(chat)
    row = chat["message_ledger_v26"][0]
    assert row["request_id"] == "r1"
    assert row["identity_conflict"] is True


def test_pass3_two_round_identity_is_preserved_after_rebuild():
    chat = _canonical()
    before = copy.deepcopy(chat["conversation_record"])
    rebuild_runtime_indexes_from_canonical(chat, None)
    after = chat["conversation_record"]
    for key in ("messages", "requests", "rounds"):
        assert after[key] == before[key]
    assert [x["round"] for x in chat["round_ledger"]] == [1, 2]
