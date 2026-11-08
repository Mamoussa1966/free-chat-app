from pathlib import Path

import pytest

import production_core_harness as harness


def test_pytest_workspace_excludes_streamlit_secrets_and_runtime_config(monkeypatch, tmp_path):
    source = tmp_path / "source"
    streamlit_dir = source / ".streamlit"
    tests_dir = source / "tests"
    streamlit_dir.mkdir(parents=True)
    tests_dir.mkdir()

    (streamlit_dir / "secrets.toml").write_text(
        'GEMINI_API_KEY = "must-not-be-copied"\n', encoding="utf-8"
    )
    (streamlit_dir / "config.toml").write_text(
        '[secrets]\nfiles = ["/outside/runtime/secrets.toml"]\n', encoding="utf-8"
    )
    (streamlit_dir / "secrets.toml.example").write_text(
        'GEMINI_API_KEY = "replace-me"\n', encoding="utf-8"
    )
    (source / ".env").write_text("GEMINI_API_KEY=must-not-be-copied\n", encoding="utf-8")
    (source / ".env.production").write_text(
        "CLOUDFLARE_API_TOKEN=must-not-be-copied\n", encoding="utf-8"
    )
    (source / "providers.py").write_text("VERSION = 'test'\n", encoding="utf-8")
    (tests_dir / "test_sample.py").write_text("def test_sample(): assert True\n", encoding="utf-8")

    monkeypatch.setattr(harness, "ROOT", source)
    destination = tmp_path / "sandbox"
    harness._copy_pytest_workspace(destination)

    assert not (destination / ".streamlit" / "secrets.toml").exists()
    assert not (destination / ".streamlit" / "config.toml").exists()
    assert not (destination / ".env").exists()
    assert not (destination / ".env.production").exists()
    assert (destination / ".streamlit" / "secrets.toml.example").is_file()
    assert (destination / "tests" / "test_sample.py").is_file()
    assert (destination / "providers.py").is_file()


def test_pytest_environment_removes_deployed_provider_settings_and_uses_isolated_home(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GEMINI_REQUEST_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("AI_COUNCIL_EXTRA_AGENTS", '[{"key":"cloudflare_workers_ai"}]')
    monkeypatch.setenv("CLOUDFLARE_WORKERS_AI_FREE_MODELS", "@cf/zai-org/glm-4.7-flash")
    monkeypatch.setenv("CLOUDFLARE_WORKERS_FREE_PLAN_CONFIRMED", "true")
    monkeypatch.setenv("SUPABASE_PROD_PUBLISHABLE_KEY", "must-not-be-inherited")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-inherited")
    project_root = tmp_path / "project"
    isolated_home = tmp_path / "isolated-home"

    env = harness._pytest_env(project_root, isolated_home)

    for key in (
        "GEMINI_REQUEST_TIMEOUT_SECONDS",
        "AI_COUNCIL_EXTRA_AGENTS",
        "CLOUDFLARE_WORKERS_AI_FREE_MODELS",
        "CLOUDFLARE_WORKERS_FREE_PLAN_CONFIRMED",
        "SUPABASE_PROD_PUBLISHABLE_KEY",
        "OPENAI_API_KEY",
    ):
        assert key not in env
    assert env["HOME"] == str(isolated_home)
    assert env["USERPROFILE"] == str(isolated_home)
    assert env["XDG_CONFIG_HOME"] == str(isolated_home / ".config")
    assert env["PYTHONPATH"] == str(project_root)
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_pytest_workspace_rejects_unapproved_symlinks(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "ordinary.txt").write_text("data", encoding="utf-8")
    target = source / "ordinary.txt"
    link = source / "unexpected-link"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable on this platform")

    monkeypatch.setattr(harness, "ROOT", source)
    with pytest.raises(harness.GateFailure, match="symlink"):
        harness._copy_pytest_workspace(tmp_path / "sandbox")
