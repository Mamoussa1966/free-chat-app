import os
from unittest.mock import patch

import main
from conversation_store import ensure_store, canonical_upsert_request, canonical_upsert_round, rebuild_runtime_indexes_from_canonical
from production_platform import conversation_persistence_audit, multi_request_regression_audit
from providers import SEATS, get_model_candidates
from message_ledger import record_message


def _chat():
    c = {"conversation_id":"conv-hotfix161", "session_id":"sess-hotfix161"}
    ensure_store(c)
    return c


def test_hotfix161_request_creation_round_base_is_monotonic_from_requests():
    c = _chat()
    canonical_upsert_request(c, {"request_id":"r1"})
    canonical_upsert_request(c, {"request_id":"r2"})
    reqs = c["conversation_record"]["requests"]
    assert [r["canonical_round_base"] for r in reqs] == [1, 2]
    assert all(r["canonical_round_allocation_contract"] == "V26.3.21-REQUEST-CREATION-MONOTONIC-ROUND/v1" for r in reqs)


def test_hotfix161_canonical_round_record_is_materialized_with_identity():
    c = _chat()
    canonical_upsert_request(c, {"request_id":"r1", "canonical_round_base":1})
    canonical_upsert_round(c, {"round_id":"conv-hotfix161:r1:r1", "request_id":"r1", "message_id":"m1", "conversation_id":"conv-hotfix161", "session_id":"sess-hotfix161", "round":1})
    row = c["conversation_record"]["rounds"][0]
    assert row["record_type"] == "CANONICAL_ROUND_RECORD"
    assert row["canonical_round_base"] == 1


def test_hotfix161_persistence_reports_authoritative_persisted_counts():
    c = _chat()
    c["request_records"] = [{"request_id":"r1", "state":"COMPLETED", "results":[{"attempt_summaries":[{}], "executed_model":"m1"}], "request_metrics":{"provider_execution_events":1}, "synthesis":{"status":"READY"}}]
    canonical_upsert_request(c, {"request_id":"r1", "message_id":"m1", "conversation_id":"conv-hotfix161", "session_id":"sess-hotfix161", "rounds_executed":1, "state":"COMPLETED", "request_metrics":{"provider_execution_events":1}, "synthesis":{"status":"READY"}})
    from conversation_store import canonical_upsert_message
    canonical_upsert_message(c, {"message_id":"m1", "request_id":"r1", "conversation_id":"conv-hotfix161", "session_id":"sess-hotfix161", "role":"user"})
    canonical_upsert_round(c, {"round_id":"conv-hotfix161:r1:r1", "request_id":"r1", "message_id":"m1", "conversation_id":"conv-hotfix161", "session_id":"sess-hotfix161", "round":1})
    audit = conversation_persistence_audit(c, "r1")
    assert audit["persisted_message_count"] == 1
    assert audit["persisted_request_count"] == 1
    assert audit["persisted_round_count"] == 1
    assert audit["counter_semantics_consistent"] is True


def test_hotfix161_hydration_rebuilds_canonical_runtime_indexes():
    c = _chat()
    canonical_upsert_request(c, {"request_id":"r1", "canonical_round_base":1})
    canonical_upsert_round(c, {"round_id":"conv-hotfix161:r1:r1", "request_id":"r1", "round":1})
    rebuild_runtime_indexes_from_canonical(c)
    assert c["canonical_runtime_indexes"]["request_ids"] == ["r1"]
    assert c["canonical_runtime_indexes"]["round_ids"] == ["conv-hotfix161:r1:r1"]


def test_hotfix161_message_round_id_is_preserved():
    c = _chat()
    row = record_message(c, "m1", "user", "x", request_id="r1", round_id="conv-hotfix161:r1:r1")
    assert row["round_id"] == "conv-hotfix161:r1:r1"
    assert c["message_ledger_v24"][0]["round_id"] == "conv-hotfix161:r1:r1"


def test_hotfix161_multi_request_audit_exposes_isolation_checks():
    c = _chat()
    c["request_records"] = [
        {"request_id":"r1", "state":"COMPLETED", "results":[{"request_id":"r1","seat_key":"deepseek","round":1}]},
        {"request_id":"r2", "state":"COMPLETED", "results":[{"request_id":"r2","seat_key":"deepseek","round":2}]},
    ]
    report = multi_request_regression_audit(c)
    assert report["status"] == "PASS"
    assert all(report["checks"].values())


def test_hotfix162_gemini_no_secret_has_no_implicit_models():
    seat = next(s for s in SEATS if s.key == "gemini")
    with patch("providers._streamlit_secret", return_value=None), patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GEMINI_FREE_MODELS", None)
        assert get_model_candidates(seat) == ()


def test_hotfix1631_all_read_only_diagnostic_variants_bypass_request_lifecycle():
    prompts = [
        "HOTFIX163.1 — REPOSITORY CANONICAL STATE BOUNDARY TEST\nREAD-ONLY",
        "HOTFIX163.1 — CLEAN TWO-RECORD CANONICAL FIXTURE TEST\nREAD-ONLY",
        "HOTFIX163.1 — READ PATH SIDE-EFFECT ISOLATION TEST\nREAD-ONLY",
    ]
    assert all(main._is_hotfix1631_read_only_diagnostic(p) for p in prompts)
    assert not main._is_hotfix1631_read_only_diagnostic("HOTFIX163.1 unrelated request")
