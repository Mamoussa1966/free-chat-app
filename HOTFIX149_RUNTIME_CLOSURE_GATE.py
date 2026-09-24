from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

REQUIRED = [
    "conversation_v25_runtime.py",
    "conversation_persistence_v26.py",
    "conversation_store.py",
    "tests/test_hotfix148_v26_3_canonical_counter_root_cause.py",
    "tests/test_hotfix149_v26_3_live_canonical_counter_runtime.py",
]


def main():
    missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
    if missing:
        print("NO-GO: missing required runtime/test files:", *missing, sep="\n- ")
        return 2
    cmd = [sys.executable, "-m", "pytest", "tests/test_hotfix148_v26_3_canonical_counter_root_cause.py", "tests/test_hotfix149_v26_3_live_canonical_counter_runtime.py", "-q"]
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("NO-GO: live canonical counter runtime gate failed")
        return result.returncode
    print("PASS: HOTFIX149 live canonical counter runtime gate")
    print("PASS: canonical counters are proven through production runtime paths, not UI projection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
