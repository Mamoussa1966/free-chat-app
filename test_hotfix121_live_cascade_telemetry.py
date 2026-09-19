from pathlib import Path


def test_hotfix121_version_identity():
    version = Path("VERSION.txt").read_text(encoding="utf-8").strip()
    assert version == "V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE"


def test_hotfix121_ui_contains_required_live_fields():
    source = Path("main.py").read_text(encoding="utf-8")
    required = [
        "LIVE Cascade attempt telemetry",
        "Request ID = {request_id}",
        "Round = {round_no}",
        "{model} → {cls} → {action}",
        "Status = {status_text}",
    ]
    for token in required:
        assert token in source


def test_hotfix121_does_not_create_execution_paths():
    source = Path("main.py").read_text(encoding="utf-8")
    fn = source[source.index("def _render_result_line"):source.index("def _render_bridge_audit")]
    assert "call_seat(" not in fn
    assert "orchestrator" not in fn.lower()
    assert "call_official(" not in fn
