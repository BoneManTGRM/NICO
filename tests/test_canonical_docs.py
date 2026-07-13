from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_canonical_documentation_exists_and_is_linked() -> None:
    readme = _read("README.md")

    for path in (
        "ARCHITECTURE.md",
        "docs/OPERATOR_GUIDE.md",
        "docs/PROJECT_STATUS.md",
        "docs/README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
    ):
        assert (ROOT / path).is_file(), path
        assert path in readme or path in _read("docs/README.md")


def test_readme_does_not_call_the_active_frontend_a_placeholder_foundation() -> None:
    readme = _read("README.md")

    assert "Frontend foundation" not in readme
    assert "merely a placeholder foundation" in readme
    assert "unified Express, Mid, and Full" in readme


def test_docs_preserve_evidence_and_human_review_boundaries() -> None:
    combined = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "ARCHITECTURE.md",
            "docs/OPERATOR_GUIDE.md",
            "docs/PROJECT_STATUS.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
        )
    )

    assert "Missing evidence is not passing evidence" in combined
    assert "human review" in combined.lower()
    assert "unauthorized" in combined.lower()
    assert "Synthetic fixtures" in combined


def test_project_status_does_not_overclaim_reparodynamics_validation() -> None:
    status = _read("docs/PROJECT_STATUS.md")
    readme = _read("README.md")

    assert "independently validated academic discipline" in status
    assert "does not represent it as independently validated academic science" in readme


def test_security_policy_contains_private_reporting_and_supported_version_guidance() -> None:
    security = _read("SECURITY.md")

    assert "Do not open a public issue" in security
    assert "Supported versions" in security
    assert "authorization or tenancy bypass" in security
    assert "false passing evidence" in security
