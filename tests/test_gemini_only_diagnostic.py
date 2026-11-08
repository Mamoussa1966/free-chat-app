from pathlib import Path
from types import SimpleNamespace

import main


def _seat(key: str, slot: int):
    return SimpleNamespace(key=key, name=key, room_slot=slot)


def test_gemini_only_diagnostic_calls_only_gemini(monkeypatch):
    seats = [_seat("gemini", 2), _seat("cloudflare_workers_ai", 8)]
    calls = []

    monkeypatch.setattr(main, "get_seats", lambda: seats)

    def fake_diagnostic(seat, credential, candidates):
        calls.append((seat.key, credential, candidates))
        return {
            "seat": seat.key,
            "status": "SUCCESS",
            "attempted_models": ["gemini-3.8-flash"],
        }

    monkeypatch.setattr(main, "diagnostic_seat", fake_diagnostic)
    result = main._run_gemini_only_diagnostic(
        {"gemini": "gemini-token", "cloudflare_workers_ai": "must-not-be-used"},
        {
            "gemini": ("gemini-3.8-flash",),
            "cloudflare_workers_ai": ("@cf/zai-org/glm-4.7-flash",),
        },
    )

    assert calls == [("gemini", "gemini-token", ("gemini-3.8-flash",))]
    assert result["seat"] == "gemini"
    assert result["status"] == "SUCCESS"


def test_gemini_only_diagnostic_fails_closed_when_seat_is_absent(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_seats",
        lambda: [_seat("cloudflare_workers_ai", 8)],
    )
    monkeypatch.setattr(
        main,
        "diagnostic_seat",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("must not dispatch")
        ),
    )

    result = main._run_gemini_only_diagnostic({}, {})

    assert result["seat"] == "gemini"
    assert result["status"] == "NOT_CONFIGURED"
    assert result["attempted_models"] == []


def test_sidebar_exposes_a_gemini_only_diagnostic_button():
    source = (
        Path(__file__).resolve().parents[1] / "main.py"
    ).read_text(encoding="utf-8")
    assert '"🧪 اختبار Gemini فقط"' in source
    assert 'key="gemini_single_provider_diagnostic"' in source
    assert "_run_gemini_only_diagnostic(credentials, model_candidates)" in source
