from pathlib import Path

def test_main_uses_atomic_canonical_lifecycle_before_dispatch():
    s=Path(Path(__file__).resolve().parents[1]/'main.py').read_text()
    assert 'canonical_create_lifecycle(' in s
    assert 'assert_canonical_lifecycle_ready(' in s
    assert s.index('canonical_create_lifecycle(') < s.index('assert_canonical_lifecycle_ready(')

def test_reconcile_request_has_session_state_transport_parameter():
    s=Path(Path(__file__).resolve().parents[1]/'conversation_v25_runtime.py').read_text()
    assert 'def reconcile_request(chat: dict, request_id: str, message_id: str, results: list[dict], synthesis: dict | None = None, session_state=None)' in s
