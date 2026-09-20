from conversation_store import ensure_store
from conversation_runtime import begin_round, finish_round
from message_ledger import record_message
from provenance_engine import record_result
from conversation_v25_runtime import ensure_v25_store, reconcile_request, authoritative_audit


def _result(rid, seat, provider, model, attempts):
    ev=[]
    for i in range(1, attempts+1):
        ev.append({
            "attempt": i, "model": model if i == attempts else f"fallback-{i}",
            "status": "SUCCESS" if i == attempts else "FAILED",
            "classification": "SUCCESS" if i == attempts else "TRANSIENT_PROVIDER_ERROR",
            "cascade_action": "SUCCESS" if i == attempts else "CASCADE_CONTINUE",
            "execution_started": True,
        })
    return {
        "request_id": rid, "round": 1, "seat": seat, "name": provider,
        "model": model, "executed_model": model, "status": "SUCCESS",
        "content": "ok", "runtime_execution_events": ev,
    }


def test_authoritative_two_message_runtime_records_are_independent():
    chat={"id":"chat", "conversation_id":"conv", "session_id":"sess", "request_records":[]}
    ensure_store(chat); ensure_v25_store(chat)

    for n, (mid, rid, seat, attempts) in enumerate([
        ("m1", "r1", "gemini", 2),
        ("m2", "r2", "deepseek", 1),
    ], start=1):
        record_message(chat, mid, "user", f"message {n}", request_id=rid)
        round_id=begin_round(chat, mid, rid, 1)
        finish_round(chat, round_id, "COMPLETED", 1)
        record_message(chat, mid, "user", f"message {n}", request_id=rid, round_id=round_id)
        rr=_result(rid, seat, "Gemini" if seat=="gemini" else "DeepSeek", "model-x", attempts)
        prov=record_result(chat, rr, mid, round_id)
        chat["result_ledger_v24"].append({
            "result_id": f"res-{rid}", "request_id": rid, "message_id": mid,
            "provider": rr["name"], "seat": seat, "model": rr["model"],
            "status": "SUCCESS", "provenance_count": len(prov),
        })
        chat["request_records"].append({
            "request_id": rid, "state": "COMPLETED",
            "request_metrics": {
                "provider_execution_events": attempts,
                "total_cascade_attempts": attempts,
            },
            "synthesis": {
                "status":"READY", "successful_seats":1,
                "successful_providers":[rr["name"]],
                "source_request_ids":[rid], "source_rounds":[1],
                "composition":"APPLICATION_OWNED_RESULT_SET",
                "provenance_count":len(prov),
            },
        })
        reconcile_request(chat, rid, mid, [rr], chat["request_records"][-1]["synthesis"])

    audit=authoritative_audit(chat)
    assert audit["message_1_id"] == "m1"
    assert audit["message_2_id"] == "m2"
    assert audit["request_1_id"] == "r1"
    assert audit["request_2_id"] == "r2"
    assert audit["round_ids_unique"] is True
    assert audit["request_isolation"] is True
    assert audit["counter_isolation"] is True
    assert audit["result_isolation"] is True
    assert audit["provenance_message_1"] == 2
    assert audit["provenance_message_2"] == 1
    assert audit["synthesis_message_1"]["composition"] == "APPLICATION_OWNED_RESULT_SET"
    assert audit["synthesis_message_2"]["composition"] == "APPLICATION_OWNED_RESULT_SET"
    assert audit["overall_authoritative_status"] == "PASS"


def test_message_ledger_relink_is_idempotent():
    chat={"id":"chat", "conversation_id":"conv", "session_id":"sess", "request_records":[]}
    ensure_store(chat)
    record_message(chat, "m1", "user", "x", request_id="r1")
    record_message(chat, "m1", "user", "x", request_id="r1", round_id="conv:r1:r1")
    record_message(chat, "m1", "user", "x", request_id="r1", round_id="conv:r1:r1")
    rows=chat["message_ledger_v24"]
    assert len(rows)==1
    assert rows[0]["request_id"]=="r1"
    assert rows[0]["round_id"]=="conv:r1:r1"
