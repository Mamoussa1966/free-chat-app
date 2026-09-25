from conversation_store import (
    ensure_store,
    canonical_upsert_message,
    canonical_upsert_request,
    canonical_upsert_round,
    canonical_audit_preflight,
    hydrate_canonical_record,
    rebuild_runtime_indexes_from_canonical,
)
from production_platform import build_v23_platform_audit
from message_ledger import record_message


class SS(dict):
    pass


def chat():
    return {
        "conversation_id": "conv-152",
        "session_id": "sess-152",
        "conversation_record": {
            "conversation_id": "conv-152",
            "session_id": "sess-152",
            "messages": [], "requests": [], "rounds": [],
        },
        "request_records": [],
        "audit_events": [],
    }


def add_turn(c, ss, n):
    mid, rid = f"m{n}", f"req{n}"
    canonical_upsert_request(c, {
        "request_id": rid,
        "message_id": mid,
        "conversation_id": c["conversation_id"],
        "session_id": c["session_id"],
        "created_at": f"2026-09-25T00:00:0{n}Z",
    }, ss)
    canonical_upsert_message(c, {
        "message_id": mid,
        "request_id": rid,
        "conversation_id": c["conversation_id"],
        "session_id": c["session_id"],
        "role": "user",
        "created_at": f"2026-09-25T00:00:0{n}Z",
    }, ss)
    canonical_upsert_round(c, {
        "round_id": f"conv-152:{rid}:r{n}",
        "request_id": rid,
        "message_id": mid,
        "conversation_id": c["conversation_id"],
        "session_id": c["session_id"],
        "round": n,
        "status": "COMPLETED",
        "created_at": f"2026-09-25T00:00:0{n}Z",
    }, ss)


def test_request_creation_owns_canonical_round_base_and_order_survives_narrow_rerun():
    c, ss = chat(), SS()
    add_turn(c, ss, 1)
    add_turn(c, ss, 2)
    assert c["conversation_record"]["requests"][0]["canonical_round_base"] == 0
    assert c["conversation_record"]["requests"][1]["canonical_round_base"] == 1

    c["conversation_record"] = {
        "conversation_id": c["conversation_id"], "session_id": c["session_id"],
        "messages": [c["conversation_record"]["messages"][-1]],
        "requests": [c["conversation_record"]["requests"][-1]],
        "rounds": [c["conversation_record"]["rounds"][-1]],
    }
    hydrate_canonical_record(c, ss)
    rebuild_runtime_indexes_from_canonical(c, ss)
    assert [x["request_id"] for x in c["request_records"]] == ["req1", "req2"]
    assert [x["round"] for x in c["round_ledger"]] == [1, 2]
    assert c["canonical_runtime_indexes"]["request_sequence"] == ["req1", "req2"]
    assert c["canonical_runtime_indexes"]["round_sequence"][-1].endswith(":r2")


def test_canonical_audit_preflight_loads_history_before_audit():
    c, ss = chat(), SS()
    add_turn(c, ss, 1)
    add_turn(c, ss, 2)
    c["conversation_record"] = {
        "conversation_id": c["conversation_id"], "session_id": c["session_id"],
        "messages": [c["conversation_record"]["messages"][-1]],
        "requests": [c["conversation_record"]["requests"][-1]],
        "rounds": [c["conversation_record"]["rounds"][-1]],
    }
    result = canonical_audit_preflight(c, ss)
    assert result["status"] == "PASS"
    assert result["canonical_store_loaded"] is True
    assert result["canonical_message_count"] == 2
    assert result["canonical_request_count"] == 2
    assert result["canonical_round_count"] == 2
    assert result["canonical_runtime_indexes_rebuilt"] is True
    assert result["identity_chain_valid"] is True


def test_missing_continuation_evidence_is_not_pass():
    c, _ = chat(), SS()
    report = build_v23_platform_audit(
        c, "missing-request", {"chars": 0, "digest": ""}, [], {"status": "PASS", "checks": {}}, {"gate": "PASS"}
    )
    assert report["continuation_runtime_gate"]["status"] == "NOT_REQUESTED"


def test_record_message_accepts_legacy_request_id_parameter():
    c, _ = chat(), SS()
    row = record_message(c, "m1", "user", "hello", request_id="req1")
    assert row["request_id"] == "req1"
    assert c["message_ledger_v24"][0]["request_id"] == "req1"
