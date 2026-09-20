from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_hotfix141_release_identity_and_scope():
    providers = read("providers.py")
    main = read("main.py")
    assert 'V23.0-HOTFIX144-PROSE-RUNTIME-TRUTH-SEPARATION-AUTHORITATIVE-GATE' in providers
    assert 'HOTFIX_VERSION = "HOTFIX144"' in main
    assert 'HOTFIX141_HARNESS=ABC' in main


def test_harness_requires_bounded_first_nonempty_line():
    main = read("main.py")
    assert 'if first.upper() != "HOTFIX141_HARNESS=ABC":' in main
    assert 'Only the first non-empty line can activate the harness' in main


def test_harness_mints_three_runtime_request_ids_sequentially():
    main = read("main.py")
    block = re.search(r'def _run_hotfix141_abc_harness.*?def _run_provider_diagnostics', main, re.S)
    assert block, "HOTFIX141 harness function missing"
    text = block.group(0)
    assert 'labels = ("A", "B", "C")' in text
    assert text.count('request_id = uuid.uuid4().hex') == 1
    assert '_run_council(' in text
    assert '[("BRIDGE_RESULT", bridge_value)]' in text


def test_harness_bridge_value_is_application_generated_not_user_prompt_extracted():
    main = read("main.py")
    block = re.search(r'def _run_hotfix141_abc_harness.*?def _run_provider_diagnostics', main, re.S)
    text = block.group(0)
    assert 'bridge_value = f"HOTFIX141_RUNTIME_{label}_{uuid.uuid4().hex}"' in text
    assert '_extract_bridge_control_values(user_prompt)' not in text


def test_normal_request_semantics_remain_single_lifecycle():
    main = read("main.py")
    assert 'if harness_abc:' in main
    assert 'results = _run_council(prompt, chat, rounds' in main
