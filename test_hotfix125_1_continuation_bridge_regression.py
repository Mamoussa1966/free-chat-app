from pathlib import Path
import copy
import main


def _chat():
    return {
        "id": "session-1251",
        "title": "test",
        "messages": [],
        "request_ids": [],
        "request_records": [{
            "request_id": "648faf6e84f244bca6f286ed7a954d81",
            "state": "COMPLETED",
            "rounds": 1,
            "rounds_executed": 1,
            "results": [{
                "seat": "gemini", "status": "SUCCESS", "request_id": "648faf6e84f244bca6f286ed7a954d81", "round": 1,
                "bridge_transaction_audit": {
                    "BRIDGE_ID": "bridge-original", "WRITE": "PASS", "VALIDATE": "PASS", "COMMIT": "PASS",
                    "BARRIER": "PASS", "READ": "PASS", "SCHEMA_VALIDATION": "PASS",
                    "BRIDGE_STATE_CONTAINS_VALUE": "YES", "USER_PROMPT_CONTAINS_VALUE": "NO",
                    "GEMINI_INPUT_PROMPT_CONTAINS_VALUE": "NO", "MATCH": "PASS",
                },
            }],
            "request_metrics": {"unique_request_ids": 1, "unique_bridge_ids": 1},
            "synthesis": {"status": "READY", "source_request_ids": ["648faf6e84f244bca6f286ed7a954d81"]},
        }],
        "history_identity_ledger": [["648faf6e84f244bca6f286ed7a954d81", 1, "gemini"]],
        "result_keys": [],
    }


def test_explicit_continuation_resolves_existing_request_only():
    c = _chat()
    rid = main._extract_continuation_request_id(
        "Continue Request ID: 648faf6e84f244bca6f286ed7a954d81 and run the V23 audit.", c
    )
    assert rid == "648faf6e84f244bca6f286ed7a954d81"
    assert len(c["request_records"]) == 1


def test_unknown_request_id_is_not_accepted_as_continuation():
    c = _chat()
    assert main._extract_continuation_request_id("CONTINUE REQUEST ID: deadbeefdeadbeefdeadbeefdeadbeef", c) == ""


def test_continuation_has_no_second_bridge_identity():
    c = _chat()
    before = copy.deepcopy(c)
    rid = main._extract_continuation_request_id("CONTINUATION REQUEST ID: 648faf6e84f244bca6f286ed7a954d81", c)
    record = main._request_record(c, rid)
    assert rid == before["request_records"][0]["request_id"]
    assert record["results"][0]["bridge_transaction_audit"]["BRIDGE_ID"] == "bridge-original"
    assert len(c["request_records"]) == 1
    assert len(c["history_identity_ledger"]) == 1


def test_hotfix125_1_release_notes_identify_patch():
    notes = Path("HOTFIX125_RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "HOTFIX125.1" in notes
    assert "REQUEST CONTINUATION + BRIDGE ISOLATION REGRESSION FIX" in notes
