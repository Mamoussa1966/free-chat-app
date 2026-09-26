from conversation_store import ensure_store
from conversation_persistence_v26 import ensure_persistence_store, persist_identity
from conversation_v25_runtime import authoritative_audit
from main import _ui_semantic_counters
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
        round_row={"round_id":"conv-157:r1:r1","request_id":"r1","message_id":"m1","conversation_id":"conv-157","session_id":"sess-157","round":1,"status":"COMPLETED","round_identity_contract":"V26.3.18-MONOTONIC-CONVERSATION-ROUND/v1"},
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
