from pathlib import Path

import providers


def test_main_deepseek_history_guard_uses_provider_identity_matcher():
    source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "_provider_identity_matches" in source
    assert 'if provider_reported_model != executed_model:\n                    st.error("⚠️ Provider identity mismatch' not in source


def test_hotfix76_identity_contract_is_strict_for_unknown_models():
    assert providers._deepseek_model_identity_matches("deepseek-v4-flash", "deepseek-flash") is True
    assert providers._deepseek_model_identity_matches("deepseek-v4-flash", "DeepSeek-V4-Flash-0731") is True
    assert providers._deepseek_model_identity_matches("deepseek-v4-flash", "some-random-model") is False
