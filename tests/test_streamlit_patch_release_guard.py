"""Regression tests for the narrowly scoped Streamlit patch release exception."""
from pathlib import Path

import build_release


ROOT = Path(__file__).resolve().parents[1]
COMMON_REQUIREMENTS = (
    "requests>=2.31,<3",
    "pytest>=8,<10",
    "cryptography==50.0.2",
)


def test_release_guard_accepts_only_the_explicit_streamlit_166_profiles():
    for version in ("1.66.0", "1.66.1"):
        profile = (f"streamlit=={version}", *COMMON_REQUIREMENTS)
        assert profile in build_release.authorized_requirements_profiles()


def test_release_guard_rejects_unapproved_dependency_or_transitive_pin_changes():
    unsafe_profiles = (
        ("streamlit==1.66.2", *COMMON_REQUIREMENTS),
        ("streamlit==1.66.1", "requests>=2.30,<3", *COMMON_REQUIREMENTS[1:]),
        ("streamlit==1.66.1", COMMON_REQUIREMENTS[0], "pytest>=7,<10", COMMON_REQUIREMENTS[2]),
        ("streamlit==1.66.1", COMMON_REQUIREMENTS[0], COMMON_REQUIREMENTS[1], "cryptography==50.0.1"),
        ("streamlit==1.66.1", *COMMON_REQUIREMENTS, "pyarrow==26.0.0"),
    )
    for profile in unsafe_profiles:
        assert profile not in build_release.authorized_requirements_profiles()


def test_candidate_requirements_match_the_approved_streamlit_patch_profile():
    actual = tuple((ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines())
    assert actual[0] == "streamlit==1.66.1"
    assert actual in build_release.authorized_requirements_profiles()
