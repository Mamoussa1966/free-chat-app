from conversation_store import canonical_audit_preflight, canonical_identity_counts
from production_platform import conversation_persistence_audit, build_v23_platform_audit


class SS(dict):
    pass


def canonical_chat():
    return {
        "id": "sess-ui", "conversation_id": "conv-153", "session_id": "sess-153",
        "messages": [
            {"role":"user","content":"one"}, {"role":"assistant","content":"provider"},
            {"role":"assistant","content":"synthesis"}, {"role":"system","content":"telemetry"},
            {"role":"assistant","content":"projection"}, {"role":"assistant","content":"projection-2"},
        ],
        "conversation_record": {
            "conversation_id":"conv-153", "session_id":"sess-153", "canonical_store_contract":"V26_3_CANONICAL_CONVERSATION_STORE",
            "canonical_store_committed":True,
            "messages":[
                {"message_id":"m1","role":"user","request_id":"r1"},
                {"message_id":"m2","role":"user","request_id":"r2"},
                {"message_id":"a1","role":"assistant","request_id":"r1"},
                {"message_id":"a2","role":"assistant","request_id":"r2"},
                {"message_id":"s1","role":"system","request_id":"r2"},
            ],
            "requests":[
                {"request_id":"r1","message_id":"m1"}, {"request_id":"r2","message_id":"m2"},
            ],
            "rounds":[
                {"round_id":"conv-153:r1:r1","request_id":"r1","message_id":"m1","round":1},
                {"round_id":"conv-153:r2:r2","request_id":"r2","message_id":"m2","round":2},
            ],
        },
        "request_records":[{
            "request_id":"r2","rounds_executed":1,
            "results":[{"status":"SUCCESS","attempt_summaries":[{"attempt":1}]}],
            "request_metrics":{"unique_request_ids":1}, "synthesis":{"status":"READY"},
        }],
    }


def test_shared_canonical_counter_contract_is_exactly_two_two_two():
    c=canonical_chat()
    assert canonical_identity_counts(c["conversation_record"]) == {
        "canonical_message_count":2,"canonical_request_count":2,"canonical_round_count":2
    }


def test_persistence_gate_ignores_ui_projection_message_count():
    c=canonical_chat()
    r=conversation_persistence_audit(c, "r2")
    assert r["status"] == "PASS"
    assert r["canonical_message_count"] == 2
    assert r["canonical_request_count"] == 2
    assert r["canonical_round_count"] == 2
    assert r["ui_projection_message_count"] == 6
    assert r["ui_projection_message_count_authoritative"] is False
    assert r["counter_semantics_consistent"] is True


def test_canonical_preflight_exposes_contract_and_never_reads_ui_projection():
    c=canonical_chat(); ss=SS({"v26_3_canonical_conversation_store": {"conv-153": {"record": c["conversation_record"], "revision": 1}}})
    c["conversation_record"]={"conversation_id":"conv-153","session_id":"sess-153","messages":[c["conversation_record"]["messages"][-1]],"requests":[c["conversation_record"]["requests"][-1]],"rounds":[c["conversation_record"]["rounds"][-1]]}
    r=canonical_audit_preflight(c, ss)
    assert r["status"] == "PASS"
    assert r["canonical_message_count"] == 2
    assert r["canonical_request_count"] == 2
    assert r["canonical_round_count"] == 2
    assert r["canonical_counter_source"] == "CANONICAL_IDENTITY_RECORDS"
    assert r["counter_semantics_consistent"] is True
    assert r["ui_projection_consulted"] is False


def test_missing_continuation_audit_is_not_proven_not_pass():
    c=canonical_chat()
    report=build_v23_platform_audit(c,"r2",{"chars":7000,"digest":"x"},[{"status":"READY"}],{"status":"PASS"},{"gate":"PASS"})
    assert report["continuation_runtime_gate"]["audit"] == {}
    assert report["continuation_runtime_gate"]["status"] == "NOT_PROVEN"
