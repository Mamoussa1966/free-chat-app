from conversation_runtime import ensure_conversation_state, begin_round
from conversation_v25_runtime import authoritative_audit
from conversation_persistence_v26 import persist_identity
from main import _authoritative_round_base


class SS(dict):
    pass


def _seed_two_message_history():
    ss = SS()
    chat = {
        "conversation_id": "conv-hf126",
        "session_id": "sess-hf126",
        "messages": [],
        "request_records": [],
        "message_ledger": [],
        "round_ledger": [],
        "conversation_record": {},
    }
    ensure_conversation_state(chat)
    for i in (1, 2):
        mid, rid = f"m{i}", f"req{i}"
        msg = {"message_id": mid, "conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "role": "user", "request_id": rid, "created_at": f"2026-09-23T10:0{i}:00Z"}
        req = {"request_id": rid, "message_id": mid, "conversation_id": chat["conversation_id"], "session_id": chat["session_id"], "state": "COMPLETED"}
        chat["messages"].append({"id": mid, "role": "user", "request_id": rid, "created_at": msg["created_at"]})
        chat["request_records"].append(req)
        persist_identity(chat, ss, message=msg, request=req)
    return chat, ss


def test_hotfix126_authoritative_round_base_comes_from_canonical_ledger():
    chat, ss = _seed_two_message_history()
    assert _authoritative_round_base(chat) == 0
    begin_round(chat, "m1", "req1", 1, ss)
    assert _authoritative_round_base(chat) == 1
    begin_round(chat, "m2", "req2", 2, ss)
    assert _authoritative_round_base(chat) == 2
    rounds = chat["conversation_record"]["rounds"]
    assert [r["round"] for r in rounds] == [1, 2]
    assert [r["round_id"].rsplit(":r", 1)[1] for r in rounds] == ["1", "2"]


def test_hotfix126_audit_proves_round_2_from_ledger_not_label():
    chat, ss = _seed_two_message_history()
    begin_round(chat, "m1", "req1", 1, ss)
    begin_round(chat, "m2", "req2", 2, ss)
    audit = authoritative_audit(chat, ss)
    assert audit["canonical_round_ordinals"] == [1, 2]
    assert audit["canonical_round_sequence_proven"] is True
    assert audit["request_1_round_1_mapping"] is True
    assert audit["request_2_round_2_mapping"] is True
    assert audit["request_2_round_1_mapping"] is False


def test_hotfix126_round_id_suffix_mismatch_fails_proof():
    chat, ss = _seed_two_message_history()
    begin_round(chat, "m1", "req1", 1, ss)
    begin_round(chat, "m2", "req2", 1, ss)
    # Deliberately corrupt the canonical second RoundRecord: numeric ordinal 2
    # must agree with the round_id suffix. The authoritative gate must detect it.
    second = chat["conversation_record"]["rounds"][1]
    second["round"] = 2
    second["round_id"] = f"{chat['conversation_id']}:req2:r1"
    # Re-commit the deliberately corrupted application-owned state.
    from conversation_store import commit_canonical_record
    commit_canonical_record(chat, ss)
    audit = authoritative_audit(chat, ss)
    assert audit["canonical_round_sequence_proven"] is False
    assert audit["conversation_runtime_audit"] != "PASS"


def test_hotfix126_real_orchestrator_assigns_second_request_round_2(monkeypatch):
    import main
    ss = SS()
    monkeypatch.setattr(main.st, "session_state", ss, raising=False)
    chat = {"id":"conv-orchestrator","messages":[],"request_records":[],"history_identity_ledger":[],"result_keys":[],"audit_events":[]}
    gem = next(s for s in main.get_seats() if s.key == "gemini")
    def fake_round(*args, **kwargs):
        return [{"status":"SUCCESS","seat":gem.key,"name":gem.name,"label":gem.label,"mode":"official","model":"m1","executed_model":"m1","provider_reported_model":"m1","content":"ok","attempted_models":["m1"],"cascade_position":1,"attempt_diagnostics":[],"request_id":kwargs.get("request_id", args[-2] if len(args) >= 2 else ""),"round":kwargs.get("round_no", 1)}]
    monkeypatch.setattr(main, "_run_round", fake_round)
    monkeypatch.setattr(main, "_provider_identity_matches", lambda *a, **k: True)
    main._run_council("first", chat, 1, {gem.key:"key"}, [], {gem.key:("m1",)}, "m1", "req1")
    main._run_council("second", chat, 1, {gem.key:"key"}, [], {gem.key:("m1",)}, "m2", "req2")
    rounds = chat["conversation_record"]["rounds"]
    assert [r["round"] for r in rounds] == [1, 2]
    assert rounds[0]["round_id"].endswith(":r1")
    assert rounds[1]["round_id"].endswith(":r2")
