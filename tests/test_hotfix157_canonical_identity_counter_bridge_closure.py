from conversation_store import ensure_store
from conversation_persistence_v26 import ensure_persistence_store, persist_identity
from conversation_v25_runtime import authoritative_audit
from main import _ui_semantic_counters
from conversation_store import canonical_upsert_message, canonical_upsert_request
from providers import _result
from providers import Seat


class SS(dict):
    pass


def _one_turn_chat():
    ss = SS(); ensure_persistence_store(ss)
    chat = {"conversation_id": "conv-157", "session_id": "sess-157", "conversation_record": {}}
    ensure_store(chat)
    persist_identity(
        chat, ss,
        message={"message_id":"m1","request_id":"r1","conversation_id":"conv-157","session_id":"sess-157","role":"user"},
        request={"request_id":"r1","message_id":"m1","conversation_id":"conv-157","session_id":"sess-157","state":"COMPLETED"},
        round_row={"round_id":"conv-157:r1:r1","request_id":"r1","message_id":"m1","conversation_id":"conv-157","session_id":"sess-157","round":1,"ordinal":1,"record_type":"CANONICAL_ROUND_RECORD","canonical_round_record_id":"conv-157:r1:r1","canonical_identity_key":"conv-157:r1:r1","status":"COMPLETED","round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
    )
    return chat, ss


def test_hotfix157_one_turn_canonical_round_evidence_closes():
    chat, ss = _one_turn_chat()
    audit = authoritative_audit(chat, ss)
    evidence = audit["canonical_round_identity_evidence"]
    assert evidence["message_1_request_1_exact"] is True
    assert evidence["request_1_round_1_exact"] is True
    assert evidence["request_1_round_generic_exact"] is True
    assert evidence["round_1_record_count"] == 1
    assert audit["canonical_request_round_binding_proven"] is True
    assert audit["canonical_round_sequence_proven"] is True
    assert audit["canonical_round_ordinals"] == [1]
    assert audit["overall_authoritative_status"] == "PASS"


def test_hotfix157_execution_started_counter_comes_from_runtime_events():
    results = [{"status":"SUCCESS", "runtime_execution_events":[
        {"execution_started":True}, {"execution_started":True}, {"execution_started":True}
    ]}, {"status":"SUCCESS", "runtime_execution_events":[{"execution_started":True}]}]
    counters = _ui_semantic_counters(results)
    assert counters["executed"] == 2
    assert counters["execution_started"] == 4
    assert counters["cascade_attempts"] == 4


def test_hotfix157_success_result_classification_is_success():
    seat = Seat(key="test", name="Test", label="Test", env_names=("TEST",), model_env=("TEST_MODELS",), endpoint="", kind="API_AGENT", room_slot=99)
    result = _result(seat, "SUCCESS", "model-x", "ok", None, 0.0, ["model-x"], authenticated=True, request_id="r1", round_no=1)
    assert result["classification"] == "SUCCESS"
    assert all(e["classification"] == "SUCCESS" for e in result["runtime_execution_events"] if e["execution_started"] is True)


def test_hotfix158_runtime_materializes_canonical_round_record_before_audit():
    from conversation_runtime import ensure_conversation_state, begin_round
    from conversation_store import load_canonical_snapshot
    ss = SS()
    chat = {"conversation_id": "conv-158", "session_id": "sess-158"}
    ensure_conversation_state(chat)
    ensure_persistence_store(ss)
    ensure_store(chat)
    rid = "req-158"
    mid = "msg-158"
    canonical_upsert_message(chat, {"message_id": mid, "request_id": rid, "conversation_id": "conv-158", "session_id": "sess-158", "role": "user"}, ss)
    canonical_upsert_request(chat, {"request_id": rid, "message_id": mid, "conversation_id": "conv-158", "session_id": "sess-158"}, ss)
    round_id = begin_round(chat, mid, rid, 1, ss)
    snap = load_canonical_snapshot(chat, ss)
    rows = [r for r in snap["rounds"] if r.get("round_id") == round_id]
    assert len(rows) == 1
    row = rows[0]
    assert row["record_type"] == "CANONICAL_ROUND_RECORD"
    assert row["canonical_round_record_id"] == round_id
    assert row["canonical_identity_key"] == "conv-158:req-158:r1"
    assert row["conversation_id"] == "conv-158"
    assert row["request_id"] == "req-158"
    assert row["ordinal"] == 1
