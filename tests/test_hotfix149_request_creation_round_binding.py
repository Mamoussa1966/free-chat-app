from conversation_store import ensure_store, canonical_upsert_message, canonical_upsert_request


def _chat():
    chat = {"conversation_id": "conv-149", "session_id": "sess-149", "conversation_record": {}}
    ensure_store(chat)
    return chat


def test_request_creation_allocates_monotonic_round_base_and_never_recalculates_from_completion_order():
    chat = _chat()
    ss = {}

    canonical_upsert_message(chat, {"message_id": "m1", "request_id": "req1", "conversation_id": "conv-149", "session_id": "sess-149", "role": "user"}, ss)
    req1 = canonical_upsert_request(chat, {"request_id": "req1", "message_id": "m1", "conversation_id": "conv-149", "session_id": "sess-149", "role": "user", "rounds": 1}, ss)

    canonical_upsert_message(chat, {"message_id": "m2", "request_id": "req2", "conversation_id": "conv-149", "session_id": "sess-149", "role": "user"}, ss)
    req2 = canonical_upsert_request(chat, {"request_id": "req2", "message_id": "m2", "conversation_id": "conv-149", "session_id": "sess-149", "role": "user", "rounds": 1}, ss)

    assert req1["canonical_round_base"] == 1
    assert req2["canonical_round_base"] == 2
    assert req1["canonical_round_allocation_contract"] == "V26.3.21-REQUEST-CREATION-MONOTONIC-ROUND/v1"

    # Simulate request 2 completing before request 1. Its allocation must remain 2.
    chat["conversation_record"]["rounds"].append({
        "round_id": "conv-149:req2:r2", "request_id": "req2", "message_id": "m2", "round": 2
    })
    chat["conversation_record"]["rounds"].append({
        "round_id": "conv-149:req1:r1", "request_id": "req1", "message_id": "m1", "round": 1
    })
    req1_again = canonical_upsert_request(chat, {"request_id": "req1", "message_id": "m1"}, ss)
    req2_again = canonical_upsert_request(chat, {"request_id": "req2", "message_id": "m2"}, ss)
    assert req1_again["canonical_round_base"] == 1
    assert req2_again["canonical_round_base"] == 2


def test_request_round_binding_is_creation_order_not_round_record_list_order():
    chat = _chat()
    ss = {}
    for mid, rid in (("m1", "req1"), ("m2", "req2")):
        canonical_upsert_message(chat, {"message_id": mid, "request_id": rid, "conversation_id": "conv-149", "session_id": "sess-149", "role": "user"}, ss)
        canonical_upsert_request(chat, {"request_id": rid, "message_id": mid, "conversation_id": "conv-149", "session_id": "sess-149", "role": "user", "rounds": 1}, ss)

    # Completion/commit order is intentionally reversed.
    chat["conversation_record"]["rounds"] = [
        {"round_id": "conv-149:req2:r2", "request_id": "req2", "message_id": "m2", "round": 2},
        {"round_id": "conv-149:req1:r1", "request_id": "req1", "message_id": "m1", "round": 1},
    ]
    reqs = {x["request_id"]: x for x in chat["conversation_record"]["requests"]}
    assert reqs["req1"]["canonical_round_base"] == 1
    assert reqs["req2"]["canonical_round_base"] == 2
