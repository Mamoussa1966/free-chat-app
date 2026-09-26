from conversation_store import canonical_create_lifecycle, hydrate_canonical_record, rebuild_runtime_indexes_from_canonical
from conversation_runtime import begin_round


def _chat(cid="conv-159", sid="sess-159"):
    return {
        "conversation_id": cid,
        "session_id": sid,
        "conversation_record": {
            "conversation_id": cid,
            "session_id": sid,
            "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
            "messages": [], "requests": [], "rounds": [],
        },
    }


def _turn(chat, state, n):
    mid, rid = f"m{n}", f"req{n}"
    canonical_create_lifecycle(chat,
        {"message_id": mid, "conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "role": "user", "request_id": rid},
        {"request_id": rid, "conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "message_id": mid, "state": "COMMITTED"},
        {"round_id": f"{chat['conversation_id']}:{rid}:r{n}", "conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "message_id": mid, "request_id": rid, "round": n, "status": "COMMITTED"},
        state)


def test_request_creation_base_is_one_then_two_and_rounds_match():
    c, state = _chat(), {}
    _turn(c, state, 1); _turn(c, state, 2)
    assert [x["canonical_round_base"] for x in c["conversation_record"]["requests"]] == [1, 2]
    assert [x["round"] for x in c["conversation_record"]["rounds"]] == [1, 2]


def test_hydration_repairs_legacy_round_two_three_to_one_two_from_request_order():
    c = _chat("conv-159b", "sess-159b")
    state = {}
    c["conversation_record"] = {
        "conversation_id": c["conversation_id"], "session_id": c["session_id"],
        "canonical_store_contract": "V26_3_CANONICAL_CONVERSATION_STORE",
        "messages": [
            {"message_id":"m1","role":"user","request_id":"req1"},
            {"message_id":"m2","role":"user","request_id":"req2"},
        ],
        "requests": [
            {"request_id":"req1","message_id":"m1","canonical_round_base":2},
            {"request_id":"req2","message_id":"m2","canonical_round_base":3},
        ],
        "rounds": [
            {"round_id":"conv-159b:req1:r2","request_id":"req1","message_id":"m1","round":2,"ordinal":2},
            {"round_id":"conv-159b:req2:r3","request_id":"req2","message_id":"m2","round":3,"ordinal":3},
        ],
        "canonical_store_committed": True,
    }
    state["v26_3_canonical_conversation_store"] = {
        c["conversation_id"]: {"record": c["conversation_record"], "revision": 1}
    }
    hydrate_canonical_record(c, state)
    rebuild_runtime_indexes_from_canonical(c, state)
    rec = c["conversation_record"]
    assert [x["round"] for x in rec["rounds"]] == [1, 2]
    assert [x["round_number"] for x in rec["rounds"]] == [1, 2]
    assert [x["canonical_round_base"] for x in rec["rounds"]] == [1, 2]
    assert [x["canonical_round_base"] for x in rec["requests"]] == [1, 2]
    assert c["canonical_runtime_indexes"]["round_sequence"] == [
        "conv-159b:req1:r1", "conv-159b:req2:r2"
    ]
