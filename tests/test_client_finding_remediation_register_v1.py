from __future__ import annotations

import io
from copy import deepcopy

import pytest

from pypdf import PdfReader

from nico.client_finding_remediation_register_v2 import (
    build_finding_remediation_register,
    finding_register_markdown,
    render_finding_register_pdf,
)


SHA = "b" * 40


@pytest.mark.parametrize("semantic_class,disposition", [
    ("source_observation", "not_dispositioned"),
    ("excluded_non_production_observation", "not_dispositioned"),
    ("source_observation", "non_actionable"),
])
def test_sample_text_cannot_promote_a_classified_source_observation(semantic_class, disposition):
    from nico.client_finding_remediation_register_v5 import build_finding_remediation_register as build
    canonical = {
        "identity": {"commit_sha": SHA}, "canonical_findings": [],
        "source_risk_observations": [{"path": "src/runner.py", "line": 7,
            "rule_id": "python_eval_exec", "semantic_class": semantic_class,
            "disposition_state": disposition, "source_excerpt": "exec(command)",
            "repository_revision": SHA}],
        "stage_summaries": [{"evidence": [
            "src/runner.py:7: python_eval_exec — Review execution.",
            "src/other.py:8: python_eval_exec — Review execution.",
        ]}],
    }
    before = deepcopy(canonical)
    register = build(canonical)
    assert [row["path"] for row in register["code_findings"]] == ["src/other.py"]
    assert canonical == before


@pytest.mark.parametrize("source", ["canonical", "scanner"])
def test_explicit_finding_survives_matching_observation_and_sample_text(source):
    from nico.client_finding_remediation_register_v5 import build_finding_remediation_register as build
    finding = {"finding_id": "explicit_review_finding", "path": "src/runner.py", "line": 7,
        "location": "src/runner.py:7", "rule_id": "python_eval_exec", "category": "static",
        "title": "Validate caller input", "status": "review_required", "source_excerpt": "exec(command)",
        "business_impact": "Caller input reaches execution.", "recommendation": "Validate caller input."}
    canonical = {"identity": {"commit_sha": SHA}, "canonical_findings": [finding] if source == "canonical" else [],
        "source_risk_observations": [{"path": "src/runner.py", "line": 7,
            "rule_id": "python_eval_exec", "semantic_class": "source_observation"}],
        "stage_summaries": [{"evidence": ["src/runner.py:7: python_eval_exec — Review execution."]}]}
    if source == "scanner":
        canonical["scanner_execution_records"] = [{"scanner_name": "semgrep", "applicable": True,
            "exact_commit_match": True, "findings": [finding]}]
    before = deepcopy(canonical)
    register = build(canonical)
    assert len(register["code_findings"]) == 1
    retained = register["code_findings"][0]
    assert retained["path"] == finding["path"] and retained["line"] == 7
    assert retained["source_excerpt"] == finding["source_excerpt"]
    assert retained["exact_commit_sha"] == SHA
    assert retained["human_disposition_required"] is True
    assert canonical == before


def _canonical() -> dict:
    return {
        "identity": {
            "repository": "example/python-service",
            "commit_sha": SHA,
            "run_id": "comprun_register",
        },
        "canonical_findings": [
            {
                "finding_id": "RISK-P1-COMPLEX",
                "priority": "P1",
                "category": "architecture",
                "status": "open",
                "title": "request handler has concentrated branching and elevated change risk",
                "location": "src/service.py:41",
                "symbol": "request_handler",
                "finding_family": "complexity-hotspot",
                "fact": "cyclomatic_complexity=36; loc=92; grade=F; method=python_ast",
                "interpretation": "High-complexity code hotspot",
                "business_impact": "Concentrated branching increases regression risk.",
                "recommendation": "Split the handler into bounded services and add characterization tests.",
                "acceptance_criteria": [
                    "request_handler complexity is at or below the approved threshold.",
                ],
                "owner_role": "Product Engineering Architect",
                "effort": "M",
                "production_scope": True,
            },
            {
                "finding_id": "RISK-P2-OPS",
                "priority": "P2",
                "category": "ci_cd",
                "status": "review_required",
                "title": "Classify recurring workflow failures",
                "fact": "Three historical workflow failures require cause classification.",
                "business_impact": "Unclassified failures obscure release reliability.",
                "recommendation": "Classify each failure and assign an owner.",
            },
        ],
        "scanner_execution_records": [
            {
                "scanner_name": "semgrep",
                "category": "static",
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "c" * 64,
                "findings": [
                    {
                        "path": "src/http_client.py",
                        "line": 27,
                        "check_id": "tls_verify_disabled",
                        "message": "Disabled TLS verification should not ship to production.",
                        "source_excerpt": "response = requests.get(url, verify=False)",
                        "severity": "high",
                    },
                    {
                        "path": "tests/test_http_client.py",
                        "line": 18,
                        "check_id": "tls_verify_disabled",
                        "message": "Test fixture intentionally uses verify=False.",
                    },
                ],
            },
            {
                "scanner_name": "gitleaks",
                "category": "secret",
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "d" * 64,
                "findings": [
                    {
                        "File": "src/settings.py",
                        "StartLine": 9,
                        "DetectorName": "Generic Password",
                        "Description": "password = super-secret-password-value",
                    }
                ],
            },
        ],
        "repository_evidence": {
            "code_signal_evidence": {
                "risk_pattern_hits": 1,
                "sample": "src/http_client.py:27: tls_verify_disabled — Disabled TLS verification should not ship to production.",
            }
        },
        "complexity_evidence": {
            "hotspots": [
                {
                    "path": "src/service.py",
                    "line": 41,
                    "name": "request_handler",
                    "cyclomatic_complexity": 36,
                    "loc": 92,
                    "grade": "F",
                    "method": "python_ast",
                }
            ]
        },
    }


def test_register_retains_exact_locations_and_separates_operational_findings() -> None:
    register = build_finding_remediation_register(_canonical())
    code = register["code_findings"]
    operational = register["operational_findings"]

    assert register["exact_commit_sha"] == SHA
    service_records = [item for item in code if item["location"] == "src/service.py:41"]
    assert len(service_records) == 1
    assert service_records[0]["duplicate_sources_consolidated"] is True
    tls_records = [item for item in code if item["location"] == "src/http_client.py:27"]
    assert len(tls_records) == 1
    tls = tls_records[0]
    assert tls["rule_id"] == "tls_verify_disabled"
    assert "verify=False" in tls["problematic_code"]
    assert "verify=False" in tls["source_excerpt"]
    assert tls["exact_commit_sha"] == SHA
    assert tls["artifact_hash"] == "c" * 64
    assert tls["human_disposition_required"] is True
    assert any(item["title"] == "Classify recurring workflow failures" for item in operational)
    assert all(item["location"] != "tests/test_http_client.py:18" for item in code)
    assert register["summary"]["excluded_non_production_count"] >= 1
    assert register["summary"]["semantic_duplicate_code_anchors_absent"] is True
    assert register["summary"]["cross_source_duplicates_consolidated"] >= 2


def test_secret_value_is_redacted_in_all_client_surfaces() -> None:
    register = build_finding_remediation_register(_canonical())
    markdown = finding_register_markdown(register, spanish=False)
    pdf = render_finding_register_pdf(register, spanish=False)
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)

    assert pdf.startswith(b"%PDF")
    assert "super-secret-password-value" not in markdown
    assert "super-secret-password-value" not in extracted
    assert "Secret value intentionally redacted" in markdown
    assert "src/settings.py:9" in markdown
    assert "src/settings.py:9" in extracted


def test_register_pdf_contains_location_rule_correction_and_verification() -> None:
    register = build_finding_remediation_register(_canonical())
    pdf = render_finding_register_pdf(register, spanish=False)
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    compact = "".join(extracted.split())

    assert "Finding and Remediation Register" in extracted
    assert "src/http_client.py:27".replace(" ", "") in compact
    assert "tls_verify_disabled" in extracted
    assert "Specific correction" in extracted
    assert "Verification" in extracted
    assert "Rollback" in extracted
    assert "Exit criteria" in extracted
    assert SHA in extracted
