from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_NAME = "NICO Comprehensive Technical Assessment"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_canonical_documentation_exists_and_is_linked() -> None:
    readme = _read("README.md")
    docs_map = _read("docs/README.md")

    for path in (
        "ARCHITECTURE.md",
        "docs/OPERATOR_GUIDE.md",
        "docs/PROJECT_STATUS.md",
        "docs/README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "MASTER_PLAN.md",
        "STATUS.md",
        "DECISIONS.md",
        "METRICS.md",
        "RUNBOOK.md",
    ):
        assert (ROOT / path).is_file(), path

    for path in (
        "ARCHITECTURE.md",
        "docs/OPERATOR_GUIDE.md",
        "docs/PROJECT_STATUS.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "MASTER_PLAN.md",
        "STATUS.md",
        "DECISIONS.md",
        "METRICS.md",
        "RUNBOOK.md",
    ):
        assert path in readme or path in docs_map


def test_readme_describes_the_active_frontend_and_one_product_truthfully() -> None:
    readme = _read("README.md")
    lowered = readme.lower()

    assert "Frontend foundation" not in readme
    assert "merely a placeholder foundation" not in readme
    assert PRODUCT_NAME in readme
    assert "one customer-facing assessment quality standard" in readme
    assert "unified Express, Mid, and Full" not in readme
    assert "express assessment" not in lowered
    assert "mid assessment" not in lowered
    assert "full assessment" not in lowered


def test_docs_preserve_evidence_and_human_review_boundaries() -> None:
    combined = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "ARCHITECTURE.md",
            "MASTER_PLAN.md",
            "RUNBOOK.md",
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
    assert "client delivery" in combined.lower()


def test_project_status_does_not_overclaim_reparodynamics_validation() -> None:
    status = _read("docs/PROJECT_STATUS.md")
    readme = _read("README.md")

    assert "NICO does not claim" in status
    assert "Reparodynamics is independently validated academic science" in status
    assert "does not represent it as independently validated academic science" in readme


def test_security_policy_contains_private_reporting_and_supported_version_guidance() -> None:
    security = _read("SECURITY.md")

    assert "Do not open a public issue" in security
    assert "Supported versions" in security
    assert "authorization or tenancy bypass" in security
    assert "false passing evidence" in security
