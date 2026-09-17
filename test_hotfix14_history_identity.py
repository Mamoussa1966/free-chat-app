import importlib


def test_history_identity_uses_request_round_and_seat():
    import main
    chat = {"messages": [], "result_keys": []}
    main._assert_unique_history_identity(chat, "RID", 1, "gemini")
    assert chat["result_keys"] == []
    assert chat["history_identity_ledger"] == [["RID", 1, "gemini"]]


def test_duplicate_history_identity_is_rejected_by_low_level_invariant():
    import main
    chat = {"messages": [], "result_keys": []}
    main._assert_unique_history_identity(chat, "RID", 1, "gemini")
    try:
        main._assert_unique_history_identity(chat, "RID", 1, "gemini")
    except RuntimeError as exc:
        assert "Duplicate history identity" in str(exc)
    else:
        raise AssertionError("duplicate history identity was accepted")


def test_different_requests_can_share_round_number():
    import main
    chat = {"messages": [], "result_keys": []}
    main._assert_unique_history_identity(chat, "RID-1", 1, "gemini")
    main._assert_unique_history_identity(chat, "RID-2", 1, "gemini")
    assert len(chat["history_identity_ledger"]) == 2


def test_council_deduplicates_duplicate_worker_results():
    import sys, types
    from unittest.mock import patch
    sys.modules.setdefault("streamlit", types.ModuleType("streamlit"))
    import main
    r = {"seat":"gemini","name":"Gemini","label":"🔑 Gemini","status":"SUCCESS","mode":"official","model":"m1","executed_model":"m1","content":"ok","attempted_models":["m1"],"request_id":"RID","round":1}
    chat={"messages":[],"result_keys":[],"history_identity_ledger":[]}
    with patch("main._run_round", return_value=[r, dict(r)]):
        out=main._run_council("x",chat,1,{},[],{"gemini":("m1",)},"u","RID")
    assert len(out)==1
    assert len(chat["messages"])==1
    assert len(chat["result_keys"])==1


def test_result_key_is_scoped_to_request_round_and_seat():
    request_id = "RID"
    round_no = 2
    seat = "gemini"
    result_key = f"{request_id}:{round_no}:{seat}"
    assert result_key == "RID:2:gemini"
