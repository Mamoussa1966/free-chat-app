"""HOTFIX150 runtime identity-binding gate."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = [
    ROOT / "tests/test_hotfix149_v26_3_live_canonical_counter_runtime.py",
    ROOT / "tests/test_hotfix150_v26_3_request_round_identity_binding.py",
]

for p in TESTS:
    if not p.is_file():
        raise SystemExit(f"MISSING_GATE_TEST:{p.name}")

cmd = [sys.executable, "-m", "pytest", "-q", *[str(p) for p in TESTS]]
result = subprocess.run(cmd, cwd=ROOT)
if result.returncode:
    raise SystemExit(result.returncode)
print("PASS: HOTFIX150 canonical Request→Round identity binding runtime gate")
print("PASS: historical selection is canonical-round-bound; created_at/list order is not identity authority")
