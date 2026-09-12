import pytest

import main


def test_request_numbers_are_distinct_even_when_model_and_round_match():
    chat = main._new_chat()
    r1 = "request-one"
    r2 = "request-two"
    chat["request_records"] = [
        {"request_id": r1, "fingerprint": "fp1", "rounds": 1},
        {"request_id": r2, "fingerprint": "fp2", "rounds": 1},
    ]
    assert main._request_display_number(chat, r1) == 1
    assert main._request_display_number(chat, r2) == 2


def test_history_identity_is_unique_across_entire_history():
    chat = main._new_chat()
    chat["messages"].append({
        "role": "assistant", "request_id": "RID", "round": 1,
        "seat": "Gemini", "seat_key": "gemini",
    })
    with pytest.raises(RuntimeError, match="Duplicate history identity invariant"):
        main._assert_unique_history_identity(chat, "RID", 1, "gemini")


def test_identity_ledger_persists_and_allows_same_model_round_for_different_requests():
    chat = main._new_chat()
    main._assert_unique_history_identity(chat, "RID1", 1, "gemini")
    main._assert_unique_history_identity(chat, "RID2", 1, "gemini")
    assert ("RID1", 1, "gemini") in main._history_identity_keys(chat)
    assert ("RID2", 1, "gemini") in main._history_identity_keys(chat)
    with pytest.raises(RuntimeError, match="Duplicate history identity invariant"):
        main._assert_unique_history_identity(chat, "RID1", 1, "gemini")


def test_invalid_history_identity_is_rejected():
    chat = main._new_chat()
    with pytest.raises(RuntimeError, match="Invalid history identity"):
        main._assert_unique_history_identity(chat, "", 1, "gemini")
