from __future__ import annotations

"""Application-facing runner for the HOTFIX117 Production Core Test Harness.

The Streamlit UI calls this module directly. No provider/LLM is asked to run
pytest or to interpret test results.
"""

from typing import Any

import production_core_harness as harness


VERSION = "V22.1-HOTFIX117-PRODUCTION-HARDENED"


def run_production_core_tests() -> tuple[int, dict[str, Any]]:
    """Execute the real local harness and return its exit code and report."""
    return harness.run()


def render_report(report: dict[str, Any]) -> str:
    """Return the canonical human-readable PASS/NO-GO report."""
    return harness.render(report)


if __name__ == "__main__":
    code, report = run_production_core_tests()
    raise SystemExit(code)
