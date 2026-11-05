"""Regression tests for the exact Streamlit patch-release allowance."""
from pathlib import Path

import build_release


ROOT = Path(__file__).resolve().parents[1]
COMMON = (
    "requests>=2.31,<3",
    "pytest>=8,<10",
    "cryptography==50.0.2",
)


def test_release_guard_accepts_only_the_two_exact_streamlit_profiles():
    allowed = build_release.authorized_requirements_profiles()
    assert ("streamlit==1.66.0", *COMMON) in allowed
    assert ("streamlit==1.66.1", *COMMON) in allowed
    assert len(allowed) == 2


def test_release_guard_rejects_unapproved_dependency_or_transitive_pin_changes():
    allowed = build_release.authorized_requirements_profiles()
    unsafe = (
        ("streamlit==1.66.2", *COMMON),
        ("streamlit==1.66.1", "requests>=2.30,<3", *COMMON[1:]),
        ("streamlit==1.66.1", COMMON[0], "pytest>=7,<10", COMMON[2]),
        ("streamlit==1.66.1", COMMON[0], COMMON[1], "cryptography==50.0.1"),
        ("streamlit==1.66.1", *COMMON, "pyarrow==26.0.0"),
    )
    assert all(profile not in allowed for profile in unsafe)


def test_candidate_requirements_match_the_approved_streamlit_patch_profile():
    actual = tuple((ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines())
    assert actual == ("streamlit==1.66.1", *COMMON)
    assert actual in build_release.authorized_requirements_profiles()
