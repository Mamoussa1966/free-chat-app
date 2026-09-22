from pathlib import Path


def test_main_preflight_restores_canonical_history_before_request_allocation():
    src=Path('main.py').read_text(encoding='utf-8')
    marker='prepare_historical_runtime(chat, st.session_state)'
    assert marker in src
    alloc=src.index('user_message_id = uuid.uuid4().hex')
    pre=src.index(marker)
    assert pre < alloc


def test_strict_historical_audit_does_not_fallback_to_current_runtime():
    src=Path('conversation_v25_runtime.py').read_text(encoding='utf-8')
    fn=src.index('def authoritative_audit')
    body=src[fn:src.index('def ', fn+4)] if 'def ' in src[fn+4:] else src[fn:]
    assert 'load_canonical_snapshot(chat, session_state)' in body
    assert 'CANONICAL_TRANSPORT_MISSING' in body
