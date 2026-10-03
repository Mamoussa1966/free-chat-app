import copy
from production_platform import multi_request_regression_audit


def _record(rid, bridge, seat="gemini"):
    return {
        "request_id": rid,
        "fingerprint": f"fp-{rid}",
        "identity_authority": "RUNTIME_REQUEST_ID",
        "state": "COMPLETED",
        "results": [{
            "request_id": rid,
            "round": 1,
            "seat": seat,
            "result_key": f"{rid}:1:{seat}",
            "execution_claim": f"{rid}:1:{seat}",
            "runtime_execution_events": [{"execution_started": True, "request_id": rid, "round": 1}],
            "bridge_transaction_audit": {"BRIDGE_ID": bridge},
        }],
        "request_metrics": {"request_id": rid, "unique_request_ids": 1},
    }


def test_hotfix135_requires_multiple_requests_for_regression_pass():
    report = multi_request_regression_audit({"request_records": [_record("A", "BR-A")]})
    assert report["status"] == "FAIL"
    assert report["checks"]["MINIMUM_INDEPENDENT_REQUESTS"] is False


def test_hotfix135_independent_requests_pass():
    chat = {"request_records": [_record("A", "BR-A"), _record("B", "BR-B")]}
    report = multi_request_regression_audit(chat)
    assert report["status"] == "PASS"
    assert report["unique_request_ids"] == 2
    assert report["unique_bridge_ids"] == 2
    assert all(report["checks"].values())


def test_hotfix135_rejects_cross_request_result_contamination():
    chat = {"request_records": [_record("A", "BR-A"), _record("B", "BR-B")]}
    contaminated = copy.deepcopy(chat)
    contaminated["request_records"][1]["results"][0]["request_id"] = "A"
    report = multi_request_regression_audit(contaminated)
    assert report["status"] == "FAIL"
    assert report["checks"]["RESULT_REQUEST_ID_ISOLATION"] is False


def test_hotfix135_rejects_bridge_reuse_across_requests():
    chat = {"request_records": [_record("A", "BR-SAME"), _record("B", "BR-SAME")]}
    report = multi_request_regression_audit(chat)
    assert report["status"] == "FAIL"
    assert report["checks"]["BRIDGE_ID_REQUEST_ISOLATION"] is False


def test_hotfix135_rejects_cross_request_execution_event():
    chat = {"request_records": [_record("A", "BR-A"), _record("B", "BR-B")]}
    chat["request_records"][1]["results"][0]["runtime_execution_events"][0]["request_id"] = "A"
    report = multi_request_regression_audit(chat)
    assert report["status"] == "FAIL"
    assert report["checks"]["NO_CROSS_REQUEST_RESULT_REFERENCE"] is False
