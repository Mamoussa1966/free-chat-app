from pathlib import Path
import main


def test_hotfix123_version_and_card_uses_runtime_request_id():
    assert Path("VERSION.txt").read_text(encoding="utf-8").strip() == "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"
    source = Path("main.py").read_text(encoding="utf-8")
    assert 'prefix = f"Request ID = `{request_id}` · " if request_id else ""' in source
    assert 'prefix = f"Request {request_no} · "' not in source


def test_hotfix123_authoritative_metrics_from_request_audit_not_prose():
    results = [
        {
            "name": "DeepSeek", "seat": "deepseek", "round": 1, "status": "SUCCESS",
            "request_id": "REQ-1",
            "attempt_diagnostics": [{"attempt": 1, "request_id": "REQ-1", "model": "deepseek-flash"}],
            "bridge_transaction_audit": {"BRIDGE_ID": "BR-1"},
        },
        {
            "name": "Gemini", "seat": "gemini", "round": 1, "status": "SUCCESS",
            "request_id": "REQ-1",
            "attempt_diagnostics": [
                {"attempt": 1, "request_id": "REQ-1", "model": "gemini-a"},
                {"attempt": 2, "request_id": "REQ-1", "model": "gemini-b"},
            ],
            "bridge_transaction_audit": {"BRIDGE_ID": "BR-1"},
        },
    ]
    events = [
        {"request_id": "REQ-1", "round_id": 1, "event_type": "PROVIDER_RESULT", "provider": "DeepSeek"},
        {"request_id": "REQ-1", "round_id": 1, "event_type": "PROVIDER_RESULT", "provider": "Gemini"},
    ]
    metrics = main._authoritative_request_metrics("REQ-1", results, events)
    assert metrics["unique_request_ids"] == 1
    assert metrics["unique_bridge_ids"] == 1
    assert metrics["total_cascade_attempts"] == 3
    assert metrics["deepseek_round1_executions"] == 1
    assert metrics["rounds"] == [1]
