from __future__ import annotations

import ast
import difflib
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path, PurePosixPath
from typing import Callable, ClassVar, Iterable, Optional


class ProposalState(Enum):
    CREATED = auto()
    AST_PASSED = auto()
    TESTS_PASSED = auto()
    READY_FOR_APPROVAL = auto()
    APPROVED = auto()
    PUSHED = auto()


class StateMachineError(Exception):
    pass


class SecurityGateError(Exception):
    pass


class GitOpsConfig:
    ALLOWLISTED_REPOS = {"r17-control-bridge/self-healing-code", "r17-control-bridge/ai-council-v22"}
    ALLOWLISTED_BRANCHES = {"main", "master", "production"}
    ALLOWED_MUTABLE_FILES = {"main.py", "app.py", "providers.py", "attachment_utils.py", "gitops_layer.py"}
    PROTECTED_FILE_PATTERNS = (re.compile(r"^\.streamlit/secrets\.toml$", re.I), re.compile(r"^\.streamlit/", re.I), re.compile(r"^\.env(?:\..*)?$", re.I), re.compile(r".*\.(?:pem|key)$", re.I), re.compile(r".*service-account.*\.json$", re.I))
    EXCLUDED_SNAPSHOT_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build"}


class SecretRedactor:
    @staticmethod
    def sanitize_exception(exc: Exception) -> str:
        value = re.sub(r"(?i)(api[_ -]?key|authorization|bearer|password|secret|token)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", str(exc))
        return re.sub(r"\s+", " ", value).strip()[:700]


class IdentityProvider:
    def __init__(self, auth_func: Optional[Callable[[str, str], bool]] = None):
        self._auth = auth_func

    def verify_identity(self, admin_id: str, role: str) -> bool:
        if not self._auth or not isinstance(admin_id, str) or not admin_id.strip() or str(role or "").upper() != "ADMIN":
            return False
        try:
            return bool(self._auth(admin_id, "ADMIN"))
        except Exception:
            return False


class CodeValidator:
    @staticmethod
    def normalize_path(path: str) -> str:
        if not isinstance(path, str) or not path or "\x00" in path:
            raise ValueError("مسار تالف.")
        value = path.replace("\\", "/")
        if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
            raise ValueError("المسارات المطلقة محظورة.")
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("المسار يجب أن يكون Git-style canonical path.")
        canonical = str(PurePosixPath(*parts))
        if canonical in {".", ""} or canonical.startswith("../"):
            raise ValueError("مسار غير صالح.")
        return canonical

    @classmethod
    def is_protected_path(cls, path: str) -> bool:
        try:
            canonical = cls.normalize_path(path)
        except ValueError:
            return True
        if canonical in GitOpsConfig.ALLOWED_MUTABLE_FILES:
            return False
        return True

    @staticmethod
    def audit_patch_ast_policy(code_str: str) -> dict:
        report = {"pass": True, "errors": []}
        forbidden_modules = {"subprocess", "importlib", "socket", "shutil", "ctypes", "multiprocessing"}
        forbidden_calls = {"exec", "eval", "compile", "system", "popen", "spawn", "__import__"}
        try:
            tree = ast.parse(code_str)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".", 1)[0]
                        if root in forbidden_modules or root == "os":
                            report["pass"] = False
                            report["errors"].append(f"استيراد محظور: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".", 1)[0]
                    if root in forbidden_modules or root == "os":
                        report["pass"] = False
                        report["errors"].append(f"استيراد محظور: {node.module}")
                elif isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                    if name in forbidden_calls:
                        report["pass"] = False
                        report["errors"].append(f"استدعاء محظور: {name}")
        except SyntaxError as exc:
            report["pass"] = False
            report["errors"].append(f"خطأ نحوي سطر {exc.lineno}: {exc.msg}")
        except Exception as exc:
            report["pass"] = False
            report["errors"].append(SecretRedactor.sanitize_exception(exc))
        return report


class DiffEngine:
    @staticmethod
    def calculate_code_hash(code_str: str) -> str:
        return hashlib.sha256(code_str.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_unified_diff(original_code: str, patched_code: str, filename: str) -> str:
        return "".join(difflib.unified_diff(original_code.splitlines(keepends=True), patched_code.splitlines(keepends=True), fromfile=f"a/{filename}", tofile=f"b/{filename}"))

    @staticmethod
    def calculate_diff_hash(diff_str: str) -> str:
        return hashlib.sha256(diff_str.encode("utf-8")).hexdigest()


class RepositorySnapshot:
    @staticmethod
    def _iter_files(base_workspace: str) -> Iterable[Path]:
        root = Path(base_workspace).resolve()
        if not root.is_dir():
            raise SecurityGateError("مساحة العمل غير موجودة أو ليست مجلداً.")
        for current, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in GitOpsConfig.EXCLUDED_SNAPSHOT_DIRS)
            for name in sorted(files):
                path = Path(current) / name
                rel = path.relative_to(root).as_posix()
                try:
                    CodeValidator.normalize_path(rel)
                    if path.is_symlink():
                        continue
                    resolved = path.resolve()
                    if root not in resolved.parents and resolved != root:
                        continue
                except (OSError, ValueError):
                    continue
                yield path

    @staticmethod
    def calculate_workspace_manifest(base_workspace: str = ".") -> str:
        root = Path(base_workspace).resolve()
        entries = []
        for path in RepositorySnapshot._iter_files(str(root)):
            rel = path.relative_to(root).as_posix()
            data = path.read_bytes()
            entries.append(f"{rel}:{len(data)}:{hashlib.sha256(data).hexdigest()}")
        return hashlib.sha256("\n".join(entries).encode()).hexdigest()


class TestGate:
    @staticmethod
    def run_candidate_tests(patched_code: str, filename: str, candidate_tests: Optional[str], workspace: str) -> dict:
        root = Path(workspace).resolve()
        if not root.is_dir():
            return {"pass": False, "exit_code": -2, "output": "workspace_missing"}
        try:
            safe = CodeValidator.normalize_path(filename)
            if safe not in GitOpsConfig.ALLOWED_MUTABLE_FILES:
                return {"pass": False, "exit_code": -2, "output": "protected_path"}
            candidate = root / safe
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(patched_code, encoding="utf-8")
            temp_test = None
            if candidate_tests:
                temp_test = root / "tests" / "test_candidate_generated.py"
                temp_test.parent.mkdir(parents=True, exist_ok=True)
                temp_test.write_text(candidate_tests, encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15, check=False)
            output = (result.stdout or "")[-6000:]
            return {"pass": result.returncode == 0, "exit_code": result.returncode, "output": output}
        except subprocess.TimeoutExpired as exc:
            return {"pass": False, "exit_code": 124, "output": SecretRedactor.sanitize_exception(exc)}
        except Exception as exc:
            return {"pass": False, "exit_code": -2, "output": SecretRedactor.sanitize_exception(exc)}


@dataclass
class Proposal:
    proposal_id: str
    filename: str
    code_hash: str
    diff_hash: str
    test_suite_hash: str = ""
    test_attestation_hash: str = ""
    state: ProposalState = ProposalState.CREATED
    workspace_manifest: str = ""
    original_code_hash: str = ""


class ApprovalSystem:
    _proposals: ClassVar[dict[str, Proposal]] = {}

    @classmethod
    def clear(cls):
        cls._proposals.clear()

    @classmethod
    def create_proposal(cls, filename: str, original_code: str, patched_code: str, workspace: str = ".") -> Proposal:
        canonical = CodeValidator.normalize_path(filename)
        if CodeValidator.is_protected_path(canonical):
            raise SecurityGateError(f"مسار غير قابل للتعديل: {canonical}")
        policy = CodeValidator.audit_patch_ast_policy(patched_code)
        if not policy["pass"]:
            raise SecurityGateError("AST policy failed: " + "; ".join(policy["errors"]))
        proposal = Proposal(uuid.uuid4().hex, canonical, DiffEngine.calculate_code_hash(patched_code), DiffEngine.calculate_diff_hash(DiffEngine.generate_unified_diff(original_code, patched_code, canonical)), workspace_manifest=RepositorySnapshot.calculate_workspace_manifest(workspace), original_code_hash=DiffEngine.calculate_code_hash(original_code))
        proposal.state = ProposalState.AST_PASSED
        cls._proposals[proposal.proposal_id] = proposal
        return proposal

    @classmethod
    def get(cls, proposal_id: str) -> Proposal:
        if proposal_id not in cls._proposals:
            raise KeyError("unknown proposal")
        return cls._proposals[proposal_id]

    @classmethod
    def verify_and_pass_tests(cls, proposal_id: str, test_suite: Optional[str], workspace: str) -> bool:
        proposal = cls.get(proposal_id)
        if proposal.state != ProposalState.AST_PASSED:
            return False
        current_manifest = RepositorySnapshot.calculate_workspace_manifest(workspace)
        if current_manifest != proposal.workspace_manifest:
            return False
        original_path = Path(workspace).resolve() / proposal.filename
        if not original_path.is_file() or DiffEngine.calculate_code_hash(original_path.read_text(encoding="utf-8")) != proposal.original_code_hash:
            return False
        patched_code = original_path.read_text(encoding="utf-8")
        result = TestGate.run_candidate_tests(patched_code, proposal.filename, test_suite, workspace)
        if not result["pass"]:
            return False
        proposal.test_suite_hash = DiffEngine.calculate_code_hash(test_suite or "")
        proposal.test_attestation_hash = hashlib.sha256(f"{proposal.proposal_id}:{proposal.code_hash}:{proposal.diff_hash}:{proposal.test_suite_hash}:{result['exit_code']}".encode()).hexdigest()
        proposal.state = ProposalState.READY_FOR_APPROVAL
        return True

    @classmethod
    def approve_proposal(cls, proposal_id: str, admin_id: str, role: str, identity: IdentityProvider) -> bool:
        proposal = cls.get(proposal_id)
        if proposal.state != ProposalState.READY_FOR_APPROVAL or not identity.verify_identity(admin_id, role):
            return False
        expected = hashlib.sha256(f"{proposal.proposal_id}:{proposal.code_hash}:{proposal.diff_hash}:{proposal.test_suite_hash}:0".encode()).hexdigest()
        if proposal.test_attestation_hash != expected:
            return False
        proposal.state = ProposalState.APPROVED
        return True
