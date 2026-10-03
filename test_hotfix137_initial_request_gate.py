import main


def test_negated_continuation_word_does_not_reject_new_request():
    chat = {"request_records": []}
    requested, record, is_cont = main._continuation_request_record(
        "HOTFIX regression test. Do not use Continuation. Create a new Request.", chat
    )
    assert requested == "" and record is None and is_cont is False


def test_explicit_continuation_request_id_remains_authoritative():
    rid = "648faf6e84f244bca6f286ed7a954d81"
    chat = {"request_records": [{"request_id": rid, "state": "COMPLETED"}]}
    requested, record, is_cont = main._continuation_request_record(
        f"CONTINUATION REQUEST ID: {rid}", chat
    )
    assert is_cont is True and requested == rid and record["request_id"] == rid


def test_unknown_explicit_continuation_id_still_fails_closed():
    rid = "deadbeefdeadbeefdeadbeefdeadbeef"
    requested, record, is_cont = main._continuation_request_record(
        f"continue Request ID: {rid}", {"request_records": []}
    )
    assert is_cont is True and requested == rid and record is None
