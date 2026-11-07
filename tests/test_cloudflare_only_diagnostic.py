from types import SimpleNamespace
from pathlib import Path

import main


def _seat(key: str, slot: int):
    return SimpleNamespace(key=key, name=key, room_slot=slot)


def test_cloudflare_only_diagnostic_calls_only_cloudflare(monkeypatch):
    seats = [_seat("gemini", 2), _seat("cloudflare_workers_ai", 8)]
    calls = []

    monkeypatch.setattr(main, "get_seats", lambda: seats)

    def fake_diagnostic(seat, credential, candidates):
        calls.append((seat.key, credential, candidates))
        return {"seat": seat.key, "status": "SUCCESS", "attempted_models": ["@cf/zai-org/glm-4.7-flash"]}

    monkeypatch.setattr(main, "diagnostic_seat", fake_diagnostic)
    result = main._run_cloudflare_only_diagnostic(
        {"gemini": "must-not-be-used", "cloudflare_workers_ai": "cf-token"},
        {"gemini": ("gemini-3.6-flash",), "cloudflare_workers_ai": ("@cf/zai-org/glm-4.7-flash",)},
    )

    assert calls == [
        ("cloudflare_workers_ai", "cf-token", ("@cf/zai-org/glm-4.7-flash",))
    ]
    assert result["seat"] == "cloudflare_workers_ai"
    assert result["status"] == "SUCCESS"


def test_cloudflare_only_diagnostic_fails_closed_when_seat_is_absent(monkeypatch):
    monkeypatch.setattr(main, "get_seats", lambda: [_seat("gemini", 2)])
    monkeypatch.setattr(
        main,
        "diagnostic_seat",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )

    result = main._run_cloudflare_only_diagnostic({}, {})

    assert result["seat"] == "cloudflare_workers_ai"
    assert result["status"] == "NOT_CONFIGURED"
    assert result["attempted_models"] == []


def test_sidebar_exposes_a_cloudflare_only_diagnostic_button():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert '"🧪 اختبار Cloudflare Workers AI فقط"' in source
    assert 'key="cloudflare_workers_ai_single_provider_diagnostic"' in source
    assert "_run_cloudflare_only_diagnostic(credentials, model_candidates)" in source
