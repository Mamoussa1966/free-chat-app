import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import gitops_layer as g


def workspace(**files):
    root = Path(tempfile.mkdtemp())
    for name, data in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")
    return root


def setup_proposal(tmp_path, original="x = 1\n", patched="x = 2\n"):
    g.ApprovalSystem.clear()
    (tmp_path / "main.py").write_text(original, encoding="utf-8")
    return g.ApprovalSystem.create_proposal("main.py", original, patched, str(tmp_path))


def approve_ready(tmp_path, proposal, suite=None):
    suite = suite or "def test_candidate():\n    assert True\n"
    assert g.ApprovalSystem.verify_and_pass_tests(proposal.proposal_id, suite, str(tmp_path))
    ident = g.IdentityProvider(lambda admin, role: admin == "admin" and role == "ADMIN")
    assert g.ApprovalSystem.approve_proposal(proposal.proposal_id, "admin", "ADMIN", ident)
    return ident


# A: canonical paths (1-8)
def test_01_normal_allowed_path():
    assert g.CodeValidator.normalize_path("main.py") == "main.py"


def test_02_parent_traversal_rejected():
    with pytest.raises(ValueError):
        g.CodeValidator.normalize_path("../main.py")


def test_03_nested_parent_traversal_rejected():
    with pytest.raises(ValueError):
        g.CodeValidator.normalize_path("tests/../main.py")


def test_04_absolute_path_rejected():
    with pytest.raises(ValueError):
        g.CodeValidator.normalize_path("/etc/passwd")


def test_05_windows_absolute_path_rejected():
    with pytest.raises(ValueError):
        g.CodeValidator.normalize_path(r"C:\\main.py")


def test_06_nul_rejected():
    with pytest.raises(ValueError):
        g.CodeValidator.normalize_path("main.py\x00evil")


def test_07_dot_component_rejected():
    with pytest.raises(ValueError):
        g.CodeValidator.normalize_path("./main.py")


def test_08_windows_parent_traversal_rejected():
    with pytest.raises(ValueError):
        g.CodeValidator.normalize_path(r"..\main.py")


# B: mutable/protected files (9-14)
def test_09_allowed_provider_file():
    assert not g.CodeValidator.is_protected_path("providers.py")


def test_10_secrets_are_protected():
    assert g.CodeValidator.is_protected_path(".streamlit/secrets.toml")


def test_11_env_is_protected():
    assert g.CodeValidator.is_protected_path(".env.production")


def test_12_pem_is_protected():
    assert g.CodeValidator.is_protected_path("tls/server.pem")


def test_13_service_account_is_protected():
    assert g.CodeValidator.is_protected_path("service-account-prod.json")


def test_14_unknown_python_is_denied_by_exact_allowlist():
    assert g.CodeValidator.is_protected_path("unknown.py")


# C: AST policy (15-23)
def test_15_exec_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("exec('x')")['pass']


def test_16_eval_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("eval('x')")['pass']


def test_17_compile_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("compile('x','x','exec')")['pass']


def test_18_subprocess_import_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("import subprocess")['pass']


def test_19_from_subprocess_run_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("from subprocess import run")['pass']


def test_20_importlib_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("import importlib")['pass']


def test_21_socket_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("import socket")['pass']


def test_22_os_system_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("import os\nos.system('x')")['pass']


def test_23_subprocess_alias_call_blocked():
    assert not g.CodeValidator.audit_patch_ast_policy("import subprocess as sp\nsp.run(['x'])")['pass']


# D: hashes/snapshot (24-30)
def test_24_same_code_same_hash():
    assert g.DiffEngine.calculate_code_hash("x\n") == g.DiffEngine.calculate_code_hash("x\n")


def test_25_same_patch_same_diff_hash():
    d1 = g.DiffEngine.generate_unified_diff("x\n", "y\n", "main.py")
    d2 = g.DiffEngine.generate_unified_diff("x\n", "y\n", "main.py")
    assert g.DiffEngine.calculate_diff_hash(d1) == g.DiffEngine.calculate_diff_hash(d2)


def test_26_one_character_code_change_changes_code_hash():
    assert g.DiffEngine.calculate_code_hash("x\n") != g.DiffEngine.calculate_code_hash("y\n")


def test_27_patch_change_changes_diff_hash():
    d1 = g.DiffEngine.generate_unified_diff("x\n", "y\n", "main.py")
    d2 = g.DiffEngine.generate_unified_diff("x\n", "z\n", "main.py")
    assert g.DiffEngine.calculate_diff_hash(d1) != g.DiffEngine.calculate_diff_hash(d2)


def test_28_same_snapshot_same_manifest():
    root = workspace(**{"main.py": "x\n", "tests/test_x.py": "def test_x(): assert True\n"})
    a = g.RepositorySnapshot.calculate_workspace_manifest(str(root))
    b = g.RepositorySnapshot.calculate_workspace_manifest(str(root))
    assert a == b


def test_29_changed_file_changes_manifest():
    root = workspace(**{"main.py": "x\n"})
    a = g.RepositorySnapshot.calculate_workspace_manifest(str(root))
    (root / "main.py").write_text("y\n", encoding="utf-8")
    b = g.RepositorySnapshot.calculate_workspace_manifest(str(root))
    assert a != b


def test_30_added_or_deleted_file_changes_manifest():
    root = workspace(**{"main.py": "x\n"})
    a = g.RepositorySnapshot.calculate_workspace_manifest(str(root))
    (root / "extra.txt").write_text("new\n", encoding="utf-8")
    b = g.RepositorySnapshot.calculate_workspace_manifest(str(root))
    assert a != b
    (root / "extra.txt").unlink()
    c = g.RepositorySnapshot.calculate_workspace_manifest(str(root))
    assert c == a


# E: candidate workspace / test gate (31-35)
def test_31_patched_file_is_written_and_used():
    root = workspace(**{"main.py": "x = 1\n", "tests/test_x.py": "def test_x(): assert open('main.py').read() == 'x = 1\\n'\n"})
    result = g.TestGate.run_candidate_tests("x = 2\n", "main.py", "def test_candidate():\n    assert open('main.py').read() == 'x = 2\\n'\n", str(root))
    assert result["pass"]


def test_32_trusted_tests_are_copied_and_executed():
    root = workspace(**{"main.py": "x = 1\n", "tests/test_x.py": "def test_x(): assert True\n"})
    result = g.TestGate.run_candidate_tests("x = 2\n", "main.py", None, str(root))
    assert result["pass"]


def test_33_passing_candidate_tests_pass_gate():
    root = workspace(**{"main.py": "x = 1\n"})
    result = g.TestGate.run_candidate_tests("x = 2\n", "main.py", "def test_candidate():\n    assert True\n", str(root))
    assert result["pass"] and result["exit_code"] == 0


def test_34_failing_candidate_tests_do_not_pass():
    root = workspace(**{"main.py": "x = 1\n"})
    result = g.TestGate.run_candidate_tests("x = 2\n", "main.py", "def test_candidate():\n    assert False\n", str(root))
    assert not result["pass"] and result["exit_code"] != 0


def test_35_timeout_does_not_pass():
    root = workspace(**{"main.py": "x = 1\n"})
    with patch("gitops_layer.subprocess.run", side_effect=g.subprocess.TimeoutExpired(cmd="pytest", timeout=15)):
        result = g.TestGate.run_candidate_tests("x = 2\n", "main.py", "def test_candidate():\n    assert True\n", str(root))
    assert not result["pass"] and result["exit_code"] == 124


# F: attestation (36)
def test_36_attestation_binds_proposal_code_diff_suite_and_result():
    root = workspace(**{"main.py": "x = 1\n"})
    proposal = setup_proposal(root)
    suite = "def test_candidate():\n    assert True\n"
    assert g.ApprovalSystem.verify_and_pass_tests(proposal.proposal_id, suite, str(root))
    expected_raw = f"{proposal.proposal_id}:{proposal.code_hash}:{proposal.diff_hash}:{proposal.test_suite_hash}:0"
    expected = hashlib.sha256(expected_raw.encode()).hexdigest()
    assert proposal.test_attestation_hash == expected
    original = proposal.test_attestation_hash
    proposal.test_attestation_hash = "tampered"
    assert proposal.test_attestation_hash != original


# G: approval/state/TOCTOU (37-39)
def test_37_unauthenticated_approval_rejected():
    root = workspace(**{"main.py": "x = 1\n"})
    proposal = setup_proposal(root)
    assert g.ApprovalSystem.verify_and_pass_tests(proposal.proposal_id, "def test_candidate():\n    assert True\n", str(root))
    bad = g.IdentityProvider(lambda admin, role: False)
    assert not g.ApprovalSystem.approve_proposal(proposal.proposal_id, "attacker", "ADMIN", bad)
    assert proposal.state == g.ProposalState.READY_FOR_APPROVAL


def test_38_tampered_approved_binding_rejected():
    root = workspace(**{"main.py": "x = 1\n"})
    proposal = setup_proposal(root)
    approve_ready(root, proposal)
    proposal.approved_diff_hash = "tampered"
    result = g.GitHubBoundary.execute_secured_push_simulated(
        proposal.proposal_id,
        "r17-control-bridge/ai-council-v22",
        "main",
        g.CredentialProvider(lambda: "github-test-token"),
        str(root),
    )
    assert not result["pass"] and result["reason"] == "approved_diff_binding_invalid"


def test_39_changed_base_manifest_after_approval_rejects_push():
    root = workspace(**{"main.py": "x = 1\n", "README.md": "stable\n"})
    proposal = setup_proposal(root)
    approve_ready(root, proposal)
    (root / "README.md").write_text("changed\n", encoding="utf-8")
    result = g.GitHubBoundary.execute_secured_push_simulated(
        proposal.proposal_id,
        "r17-control-bridge/ai-council-v22",
        "main",
        g.CredentialProvider(lambda: "github-test-token"),
        str(root),
    )
    assert not result["pass"] and result["reason"] == "workspace_manifest_changed"
