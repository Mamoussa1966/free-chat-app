from conversation_runtime import ensure_conversation_state, begin_round
from conversation_v25_runtime import authoritative_audit
from conversation_persistence_v26 import persist_identity


class SS(dict):
    pass


def _seed_two_message_history():
    ss = SS()
    chat = {
        "conversation_id": "conv-hf127",
        "session_id": "sess-hf127",
        "messages": [],
        "request_records": [],
        "message_ledger": [],
        "round_ledger": [],
        "conversation_record": {},
    }
    ensure_conversation_state(chat)
    for i in (1, 2):
        mid, rid = f"m{i}", f"req{i}"
        created = f"2026-09-23T10:0{i}:00Z"
        msg = {
            "message_id": mid, "conversation_id": chat["conversation_id"],
            "session_id": chat["session_id"], "role": "user",
            "request_id": rid, "created_at": created,
        }
        req = {
            "request_id": rid, "message_id": mid,
            "conversation_id": chat["conversation_id"],
            "session_id": chat["session_id"], "state": "COMPLETED",
            "created_at": created,
        }
        chat["messages"].append({"id": mid, "role": "user", "request_id": rid, "created_at": created})
        chat["request_records"].append(req)
        persist_identity(chat, ss, message=msg, request=req)
    begin_round(chat, "m1", "req1", 1, ss)
    begin_round(chat, "m2", "req2", 2, ss)
    return chat, ss


def test_hotfix127_exact_canonical_request_round_evidence_is_required():
    chat, ss = _seed_two_message_history()
    audit = authoritative_audit(chat, ss)
    evidence = audit["canonical_round_identity_evidence"]
    assert evidence["message_1_request_1_exact"] is True
    assert evidence["message_2_request_2_exact"] is True
    assert evidence["request_1_round_1_exact"] is True
    assert evidence["request_2_round_2_exact"] is True
    assert evidence["request_2_round_1_exact"] is False
    assert evidence["round_1_record_count"] == 1
    assert evidence["round_2_record_count"] == 1
    assert audit["request_2_round_2_mapping"] is True
    assert audit["request_2_round_1_mapping"] is False
    assert audit["canonical_round_sequence_proven"] is True
    assert audit["conversation_runtime_audit"] == "PASS"


def test_hotfix127_wrong_request2_round1_mapping_fails_closed():
    chat, ss = _seed_two_message_history()
    from conversation_store import canonical_history_hash
    root = ss["v26_3_canonical_conversation_store"][chat["conversation_id"]]
    row = root["record"]["rounds"][1]
    row["round"] = 1
    row["round_id"] = f"{chat['conversation_id']}:req2:r1"
    root["rounds"] = root["record"]["rounds"]
    root["history_hash"] = canonical_history_hash(root["record"])
    audit = authoritative_audit(chat, ss)
    assert audit["request_2_round_2_mapping"] is False
    assert audit["request_2_round_1_mapping"] is True
    assert audit["canonical_round_sequence_proven"] is False
    assert audit["conversation_runtime_audit"] == "FAIL"
    assert audit["overall_authoritative_status"] == "NOT_PROVEN"


def test_hotfix127_duplicate_request_binding_is_not_resolved_by_latest_row():
    chat, ss = _seed_two_message_history()
    from conversation_store import canonical_history_hash
    root = ss["v26_3_canonical_conversation_store"][chat["conversation_id"]]
    duplicate = dict(root["record"]["requests"][1])
    duplicate["request_id"] = "req2-duplicate"
    root["record"]["requests"].append(duplicate)
    root["requests"] = root["record"]["requests"]
    root["history_hash"] = canonical_history_hash(root["record"])
    audit = authoritative_audit(chat, ss)
    assert audit["canonical_round_sequence_proven"] is False
    assert audit["conversation_runtime_audit"] in {"NOT_PROVEN", "FAIL"}


def test_hotfix127_extra_round_record_fails_exact_two_contract():
    chat, ss = _seed_two_message_history()
    from conversation_store import canonical_history_hash
    root = ss["v26_3_canonical_conversation_store"][chat["conversation_id"]]
    extra = dict(root["record"]["rounds"][1])
    extra["round_id"] = f"{chat['conversation_id']}:req2:r3"
    extra["round"] = 3
    root["record"]["rounds"].append(extra)
    root["rounds"] = root["record"]["rounds"]
    root["history_hash"] = canonical_history_hash(root["record"])
    audit = authoritative_audit(chat, ss)
    assert audit["canonical_round_sequence_proven"] is False
    assert audit["conversation_runtime_audit"] in {"NOT_PROVEN", "FAIL"}
