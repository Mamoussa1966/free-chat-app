import os

from providers.seat_provider import SEATS
from audit.logger import _safe_error


def test_five_official_seats():
    assert [s.name for s in SEATS] == ['ChatGPT', 'Gemini', 'Claude', 'Grok', 'Kimi']


def test_grok_alias():
    from providers.seat_provider import _key
    old = os.environ.get('GROK_API_KEY')
    os.environ['GROK_API_KEY'] = 'test-grok-key'
    seat = next(s for s in SEATS if s.name == 'Grok')
    assert _key(seat) == 'test-grok-key'
    if old is None:
        os.environ.pop('GROK_API_KEY', None)
    else:
        os.environ['GROK_API_KEY'] = old


def test_audit_redaction():
    assert '[REDACTED]' in _safe_error('request failed sk-proj-ABC123456789012345')
