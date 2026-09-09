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
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from pathlib import Path, PurePosixPath
from typing import Callable, ClassVar, Dict, Iterable, Optional


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
    ALLOWLISTED_REPOS = {
        "r17-control-bridge/self-healing-code",
        "r17-control-bridge/ai-council-v22",
    }
    ALLOWLISTED_BRANCHES = {"main", "master", "production"}
    ALLOWED_MUTABLE_FILES = {
        "main.py",
        "app.py",
        "providers.py",
        "attachment_utils.py",
        "gitops_layer.py",
    }
    PROTECTED_FILE_PATTERNS = (
        re.compile(r"^\.streamlit/secrets\.toml$", re.I),
        re.compile(r"^\.streamlit/", re.I),
        re.compile(r"^\.env(?:\..*)?$", re.I),
        re.compile(r".*\.(?:pem|key)$", re.I),
        re.compile(r"(?:^|/)service-account.*\.json$", re.I),
        re.compile(r"(?:^|/)(?:credentials|secrets?)(?:\..*)?$", re.I),
    )
    ALLOWED_TEST_DIRECTORIES = {"tests", "temp_tests"}
    EXCLUDED_SNAPSHOT_DIRS = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "node_modules",
    }
    MAX_FILE_BYTES = 500 * 1024
    MAX_PATCH_BYTES = 100 * 1024
    MAX_EXECUTION_SECONDS = 15
    APPROVAL_EXPIRATION_MINUTES = 30
    MAX_OUTPUT_BYTES = 200_000


class SecretRedactor:
    SECRET_PATTERNS = (
        re.compile(r"ghp_[A-Za-z0-9]{20,255}"),
        re.compile(r"github_pat_[A-Za-z0-9_]{20,255}"),
        re.compile(r"AIzaSy[A-Za-z0-9_-]{20,255}"),
        re.compile(r"sk-[A-Za-z0-9_-]{20,255}"),
        re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{20,}", re.I),
    )

    @classmethod
    def redact(cls, text: str) -> str:
        value = str(text or "")
        for pattern in cls.SECRET_PATTERNS:
            value = pattern.sub("[REDACTED]", value)
        return value

    @classmethod
    def sanitize_exception(cls, exception: Exception) -> str:
        return cls.redact(str(exception))


class CredentialProvider:
    def __init__(self, provider_func: Optional[Callable[[], str]] = None):
        self._func = provider_func

    def get_credential(self) -> str:
        if not self._func:
            return ""
        value = self._func()
        return value if isinstance(value, str) else ""


class IdentityProvider:
    def __init__(self, auth_func: Optional[Callable[[str, str], bool]] = None):
        self._auth = auth_func

    def verify_identity(self, admin_id: str, role: str) -> bool:
        if not self._auth or not isinstance(admin_id, str) or not admin_id.strip():
            return False
        if str(role or "").upper() != "ADMIN":
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
        forbidden_modules = {"subprocess", "importlib", "socket", "shutil"}
        forbidden_calls = {
            "exec", "eval", "compile", "system", "popen", "spawn", "__import__",
        }
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
                    if isinstance(node.func, ast.Name):
                        name = node.func.id
                        if name in forbidden_calls:
                            report["pass"] = False
                            report["errors"].append(f"استدعاء محظور: {name}")
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr in forbidden_calls:
                            report["pass"] = False
                            report["errors"].append(f"استدعاء محظور: {node.func.attr}")
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
        return "".join(
            difflib.unified_diff(
                original_code.splitlines(keepends=True),
                patched_code.splitlines(keepends=True),
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
            )
        )

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
                try:
                    rel = path.relative_to(root).as_posix()
                except ValueError as exc:
                    raise SecurityGateError("فشل تحديد مسار نسبي آمن.") from exc
                try:
                    CodeValidator.normalize_path(rel)
                except ValueError:
                    continue
                yield path

    @staticmethod
    def calculate_workspace_manifest(base_workspace: str = ".") -> str:
        entries = []
        try:
            root = Path(base_workspace).resolve()
            for path in RepositorySnapshot._iter_files(str(root)):
                rel = path.relative_to(root).as_posix()
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                entries.append(f"{rel}:{len(data)}:{digest}")
            manifest = "\n".join(entries).encode("utf-8")
            return hashlib.sha256(manifest).hexdigest()
        except SecurityGateError:
            raise
        except Exception as exc:
            raise SecurityGateError(
                f"فشل توليد بصمة Manifest: {SecretRedactor.sanitize_exception(exc)}"
            ) from exc

    @staticmethod
    def copy_safe_workspace(source: str, destination: str) -> None:
        src_root = Path(source).resolve()
        dst_root = Path(destination).resolve()
        if not src_root.is_dir():
            raise SecurityGateError("المصدر ليس مساحة عمل صالحة.")
        for path in RepositorySnapshot._iter_files(str(src_root)):
            rel = path.relative_to(src_root).as_posix()
            if any(p.match(rel) for p in GitOpsConfig.PROTECTED_FILE_PATTERNS):
                continue
            target = dst_root / Path(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


class TestGate:
    @staticmethod
    def _test_path_allowed(path: str) -> bool:
        try:
            canonical = CodeValidator.normalize_path(path)
        except ValueError:
            return False
        first = canonical.split("/", 1)[0]
        return first in GitOpsConfig.ALLOWED_TEST_DIRECTORIES and canonical.endswith(".py")

    @staticmethod
    def run_candidate_tests(
        patched_code: str,
        filename: str,
        test_suite_code: Optional[str] = None,
        base_workspace: str = ".",
        test_path: str = "",
    ) -> dict:
        report = {"pass": False, "exit_code": -1, "output": ""}
        canonical_file = CodeValidator.normalize_path(filename)
        if CodeValidator.is_protected_path(canonical_file):
            raise SecurityGateError("لا يسمح باختبار ملف غير قابل للتعديل.")
        if len(patched_code.encode("utf-8")) > GitOpsConfig.MAX_FILE_BYTES:
            raise SecurityGateError("الرقعة تتجاوز حد حجم الملف.")
        with tempfile.TemporaryDirectory(prefix="gitops-candidate-") as temp_dir:
            try:
                RepositorySnapshot.copy_safe_workspace(base_workspace, temp_dir)
                target = Path(temp_dir) / canonical_file
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(patched_code, encoding="utf-8")

                if test_suite_code is not None:
                    test_rel = test_path or f"temp_tests/test_{Path(canonical_file).name}"
                    if not TestGate._test_path_allowed(test_rel):
                        raise SecurityGateError("مسار الاختبار غير مسموح.")
                    test_target = Path(temp_dir) / CodeValidator.normalize_path(test_rel)
                    test_target.parent.mkdir(parents=True, exist_ok=True)
                    test_target.write_text(test_suite_code, encoding="utf-8")
                    test_args = [str(test_target), "-v"]
                else:
                    tests_dir = Path(temp_dir) / "tests"
                    if not tests_dir.is_dir():
                        raise SecurityGateError("لا توجد مجموعة tests موثوقة داخل اللقطة.")
                    test_args = ["tests", "-q"]

                env = os.environ.copy()
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", *test_args],
                    cwd=temp_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=GitOpsConfig.MAX_EXECUTION_SECONDS,
                    env=env,
                    check=False,
                )
                output = (result.stdout or "") + "\n" + (result.stderr or "")
                output = SecretRedactor.redact(output)
                report["exit_code"] = result.returncode
                report["output"] = output[: GitOpsConfig.MAX_OUTPUT_BYTES]
                report["pass"] = result.returncode == 0
            except subprocess.TimeoutExpired:
                report.update(exit_code=124, output="❌ تجاوزت اختبارات المرشح المهلة المحددة.")
            except SecurityGateError:
                raise
            except Exception as exc:
                report["output"] = f"فشل تشغيل بيئة الاختبار: {SecretRedactor.sanitize_exception(exc)}"
        return report


@dataclass
class PatchProposal:
    proposal_id: str
    filename: str
    original_code: str
    patched_code: str
    diff_str: str
    diff_hash: str
    code_hash: str
    base_code_hash: str
    base_workspace_manifest_hash: str
    tested_code_hash: str = ""
    tested_diff_hash: str = ""
    test_suite_hash: str = ""
    test_attestation_hash: str = ""
    approved_diff_hash: str = ""
    approved_code_hash: str = ""
    approved_test_attestation_hash: str = ""
    is_approved: bool = False
    approved_by_id: str = ""
    approved_role: str = ""
    approved_at: Optional[datetime] = None
    expiration_time: Optional[datetime] = None
    state: ProposalState = ProposalState.CREATED
    metadata: dict = field(default_factory=dict)

    def _transition_to(self, new_state: ProposalState) -> None:
        allowed = {
            ProposalState.CREATED: {ProposalState.AST_PASSED},
            ProposalState.AST_PASSED: {ProposalState.TESTS_PASSED},
            ProposalState.TESTS_PASSED: {ProposalState.READY_FOR_APPROVAL},
            ProposalState.READY_FOR_APPROVAL: {ProposalState.APPROVED},
            ProposalState.APPROVED: {ProposalState.PUSHED},
            ProposalState.PUSHED: set(),
        }
        if new_state not in allowed[self.state]:
            raise StateMachineError(
                f"انتقال غير قانوني من {self.state.name} إلى {new_state.name}."
            )
        self.state = new_state


class ApprovalSystem:
    _proposals: ClassVar[Dict[str, PatchProposal]] = {}
    _lock: ClassVar[threading.RLock] = threading.RLock()

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._proposals.clear()

    @classmethod
    def create_proposal(
        cls,
        filename: str,
        original_code: str,
        patched_code: str,
        base_workspace: str = ".",
    ) -> PatchProposal:
        canonical = CodeValidator.normalize_path(filename)
        if CodeValidator.is_protected_path(canonical):
            raise ValueError(f"مسار غير قابل للتعديل: {canonical}")
        if not isinstance(original_code, str) or not isinstance(patched_code, str):
            raise ValueError("المحتوى يجب أن يكون نصاً.")
        if len(patched_code.encode("utf-8")) > GitOpsConfig.MAX_FILE_BYTES:
            raise ValueError("الملف يتجاوز الحجم المسموح.")
        diff = DiffEngine.generate_unified_diff(original_code, patched_code, canonical)
        if len(diff.encode("utf-8")) > GitOpsConfig.MAX_PATCH_BYTES:
            raise ValueError("الفروقات تتجاوز الحجم المسموح.")
        ast_result = CodeValidator.audit_patch_ast_policy(patched_code)
        if not ast_result["pass"]:
            raise StateMachineError("فشل فحص AST: " + "; ".join(ast_result["errors"]))

        proposal = PatchProposal(
            proposal_id=f"PROP-{uuid.uuid4().hex}",
            filename=canonical,
            original_code=original_code,
            patched_code=patched_code,
            diff_str=diff,
            diff_hash=DiffEngine.calculate_diff_hash(diff),
            code_hash=DiffEngine.calculate_code_hash(patched_code),
            base_code_hash=DiffEngine.calculate_code_hash(original_code),
            base_workspace_manifest_hash=RepositorySnapshot.calculate_workspace_manifest(base_workspace),
            expiration_time=datetime.now(timezone.utc)
            + timedelta(minutes=GitOpsConfig.APPROVAL_EXPIRATION_MINUTES),
        )
        proposal._transition_to(ProposalState.AST_PASSED)
        with cls._lock:
            cls._proposals[proposal.proposal_id] = proposal
        return proposal

    @classmethod
    def verify_and_pass_tests(
        cls,
        proposal_id: str,
        test_suite_code: Optional[str] = None,
        base_workspace: str = ".",
        test_path: str = "",
    ) -> bool:
        with cls._lock:
            proposal = cls._proposals.get(proposal_id)
            if not proposal or proposal.state != ProposalState.AST_PASSED:
                return False
            code_hash = proposal.code_hash
            diff_hash = proposal.diff_hash
        result = TestGate.run_candidate_tests(
            proposal.patched_code,
            proposal.filename,
            test_suite_code,
            base_workspace,
            test_path,
        )
        if not result["pass"]:
            return False
        suite_hash = DiffEngine.calculate_code_hash(test_suite_code or "TRUSTED_TESTS_DIRECTORY")
        attestation_raw = (
            f"{proposal.proposal_id}:{code_hash}:{diff_hash}:{suite_hash}:"
            f"{result['exit_code']}"
        )
        attestation = DiffEngine.calculate_code_hash(attestation_raw)
        with cls._lock:
            proposal.tested_code_hash = code_hash
            proposal.tested_diff_hash = diff_hash
            proposal.test_suite_hash = suite_hash
            proposal.test_attestation_hash = attestation
            proposal._transition_to(ProposalState.TESTS_PASSED)
            proposal._transition_to(ProposalState.READY_FOR_APPROVAL)
        return True

    @classmethod
    def approve_proposal(
        cls,
        proposal_id: str,
        admin_id: str,
        role: str,
        id_provider: IdentityProvider,
    ) -> bool:
        with cls._lock:
            proposal = cls._proposals.get(proposal_id)
            if not proposal or proposal.state != ProposalState.READY_FOR_APPROVAL:
                return False
            if proposal.expiration_time is None or datetime.now(timezone.utc) > proposal.expiration_time:
                return False
        if not id_provider.verify_identity(admin_id, role):
            return False
        with cls._lock:
            proposal = cls._proposals.get(proposal_id)
            if not proposal or proposal.state != ProposalState.READY_FOR_APPROVAL:
                return False
            proposal.approved_diff_hash = proposal.diff_hash
            proposal.approved_code_hash = proposal.code_hash
            proposal.approved_test_attestation_hash = proposal.test_attestation_hash
            proposal.is_approved = True
            proposal.approved_by_id = admin_id
            proposal.approved_role = "ADMIN"
            proposal.approved_at = datetime.now(timezone.utc)
            proposal._transition_to(ProposalState.APPROVED)
        return True

    @classmethod
    def get_proposal(cls, proposal_id: str) -> Optional[PatchProposal]:
        with cls._lock:
            return cls._proposals.get(proposal_id)


class GitHubBoundary:
    @staticmethod
    def validate_target(repo: str, branch: str) -> bool:
        return repo in GitOpsConfig.ALLOWLISTED_REPOS and branch in GitOpsConfig.ALLOWLISTED_BRANCHES

    @classmethod
    def execute_secured_push_simulated(
        cls,
        proposal_id: str,
        repo: str,
        branch: str,
        cred_provider: CredentialProvider,
        base_workspace: str = ".",
    ) -> dict:
        with ApprovalSystem._lock:
            proposal = ApprovalSystem._proposals.get(proposal_id)
            if not proposal:
                return {"pass": False, "reason": "proposal_not_found"}
            if proposal.state != ProposalState.APPROVED:
                return {"pass": False, "reason": "proposal_not_approved"}
            if proposal.expiration_time is None or datetime.now(timezone.utc) > proposal.expiration_time:
                return {"pass": False, "reason": "approval_expired"}
            if not cls.validate_target(repo, branch):
                return {"pass": False, "reason": "target_not_allowlisted"}
            if not proposal.is_approved:
                return {"pass": False, "reason": "approval_flag_invalid"}
            if proposal.code_hash != proposal.approved_code_hash:
                return {"pass": False, "reason": "approved_code_binding_invalid"}
            if proposal.diff_hash != proposal.approved_diff_hash:
                return {"pass": False, "reason": "approved_diff_binding_invalid"}
            if proposal.test_attestation_hash != proposal.approved_test_attestation_hash:
                return {"pass": False, "reason": "approved_attestation_binding_invalid"}
            if proposal.tested_code_hash != proposal.code_hash or proposal.tested_diff_hash != proposal.diff_hash:
                return {"pass": False, "reason": "test_binding_invalid"}
            if not proposal.test_suite_hash or not proposal.test_attestation_hash:
                return {"pass": False, "reason": "missing_test_attestation"}
            if not cred_provider.get_credential():
                return {"pass": False, "reason": "credential_missing"}

            current_manifest = RepositorySnapshot.calculate_workspace_manifest(base_workspace)
            if current_manifest != proposal.base_workspace_manifest_hash:
                return {"pass": False, "reason": "workspace_manifest_changed"}

            current_file = Path(base_workspace) / proposal.filename
            if not current_file.is_file():
                return {"pass": False, "reason": "base_file_missing"}
            current_code = current_file.read_text(encoding="utf-8")
            if DiffEngine.calculate_code_hash(current_code) != proposal.base_code_hash:
                return {"pass": False, "reason": "base_file_changed"}

            simulated_payload = (
                f"{repo}:{branch}:{proposal.proposal_id}:{proposal.filename}:"
                f"{proposal.base_workspace_manifest_hash}:{proposal.diff_hash}:"
                f"{proposal.approved_test_attestation_hash}"
            )
            simulated_sha = hashlib.sha256(simulated_payload.encode("utf-8")).hexdigest()
            proposal.metadata["simulated_commit_sha"] = simulated_sha
            proposal._transition_to(ProposalState.PUSHED)
            return {
                "pass": True,
                "simulated": True,
                "commit_sha": simulated_sha,
                "proposal_id": proposal.proposal_id,
            }
