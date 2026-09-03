from __future__ import annotations

import io

from pypdf import PdfReader

from nico.candidate_lineage_migration_v1 import apply_candidate_lineage, lineage_keys
from nico.candidate_phase1_report_workload_v1 import (
    render_phase1_evidence_review_gate_pdf,
)
from nico.candidate_phase1_report_workload_text_v1 import workload_markdown
from nico.candidate_phase1_workload_refinement_v1 import (
    refine_candidate_review_workload,
    scan_assessment_subject,
)


def _candidate(
    candidate_id: str,
    *,
    category: str = "static",
    scanner: str = "bandit",
    rule: str = "B105",
    path: str = "nico/example.py",
    line: int = 10,
    severity: str = "medium",
    verdict: str = "needs_review",
    confidence: str = "low",
    proof_gaps: list[str] | None = None,
    evidence_quality: str = "exact_source",
    route: str = "HUMAN_TECHNICAL_REVIEW",
    evidence_changed: bool = False,
    occurrence_count: int = 1,
    dependency: tuple[str, str, str, str] | None = None,
) -> dict:
    item = {
        "candidate_id": candidate_id,
        "finding_id": candidate_id,
        "raw_fingerprint": f"fingerprint-{candidate_id}",
        "category": category,
        "scanner": scanner,
        "rule_id": rule,
        "rule": rule,
        "source_path": path,
        "path": path,
        "line": line,
        "severity": severity,
        "evidence_quality": evidence_quality,
        "occurrence_count": occurrence_count,
        "technical_triage_verdict": verdict,
        "technical_triage_confidence": confidence,
        "technical_triage_rationale_code": (
            "static_exploitability_unresolved"
            if category == "static"
            else "dependency_reachability_or_scope_unresolved"
        ),
        "technical_triage_proof_gaps": proof_gaps
        if proof_gaps is not None
        else ["first_party_reachability", "existing_mitigation_assessment"],
        "production_test_development_scope": "production",
        "review_routing_class": route,
        "evidence_changed": evidence_changed,
    }
    if dependency is not None:
        package, version, ecosystem, advisory = dependency
        item.update(
            {
                "dependency_package": package,
                "dependency_version": version,
                "dependency_ecosystem": ecosystem,
                "advisory": advisory,
            }
        )
    return item


def _register(findings: list[dict]) -> dict:
    total = sum(int(item.get("occurrence_count") or 1) for item in findings)
    return {
        "findings": findings,
        "technical_triage": {
            "status": "complete",
            "fresh_technical_triage_completed": total,
            "workload_metrics": {
                "total_candidates": total,
                "technical_triage_completed": total,
                "technical_triage_pending": 0,
                "technical_triage_coverage_pct": 100.0,
                "quality_control_sample_pool": 0,
                "stable_carry_forward_count": 0,
            },
        },
    }


def _baseline_record(record: dict, candidate_id: str) -> list:
    keys = lineage_keys(record)
    return [
        keys["exact"],
        keys["semantic"],
        keys["group"],
        keys["line"],
        candidate_id,
        "source_review_required",
        "OLD-CLUSTER",
    ]


def test_default_project_placeholder_restores_repository_only_lineage() -> None:
    current = {
        "finding_id": "CURRENT",
        "candidate_id": "CURRENT",
        "category": "static",
        "scanner": "bandit",
        "rule_id": "B105",
        "source_path": "nico/example.py",
        "line": 10,
        "evidence": "hardcoded password string",
        "occurrence_count": 1,
    }
    subject, normalization = scan_assessment_subject(
        {
            "repository": "BoneManTGRM/NICO",
            "project_id": "default_project",
        }
    )
    baseline = {
        "s": "nico.candidate-lineage-baseline.v2",
        "r": "BoneManTGRM/NICO",
        "c": "a" * 40,
        "n": 1,
        "a": "none",
        "x": [_baseline_record(current, "PRIOR")],
    }
    result = apply_candidate_lineage(
        {"assessment_subject": subject, "findings": [current]},
        baseline=baseline,
    )

    assert subject == {"repository": "bonemantgrm/nico"}
    assert normalization["ignored_optional_placeholders"] == {
        "project_id": "default_project"
    }
    assert result["candidate_lineage"]["assessment_subject_match"] is True
    assert result["findings"][0]["lineage_status"] == "carried_forward_exact"
    assert result["findings"][0]["prior_candidate_id"] == "PRIOR"


def test_real_project_identity_remains_fail_closed() -> None:
    current = {
        "finding_id": "CURRENT",
        "candidate_id": "CURRENT",
        "category": "static",
        "scanner": "bandit",
        "rule_id": "B105",
        "source_path": "nico/example.py",
        "line": 10,
        "evidence": "hardcoded password string",
        "occurrence_count": 1,
    }
    subject, normalization = scan_assessment_subject(
        {"repository": "BoneManTGRM/NICO", "project_id": "client-project-42"}
    )
    baseline = {
        "s": "nico.candidate-lineage-baseline.v2",
        "r": "BoneManTGRM/NICO",
        "c": "a" * 40,
        "n": 1,
        "a": "none",
        "x": [_baseline_record(current, "PRIOR")],
    }
    result = apply_candidate_lineage(
        {"assessment_subject": subject, "findings": [current]},
        baseline=baseline,
    )

    assert normalization["ignored_optional_placeholders"] == {}
    assert subject["project_id"] == "client-project-42"
    assert result["candidate_lineage"]["assessment_subject_match"] is False
    assert result["candidate_lineage"]["carried_forward_total"] == 0
    assert result["findings"][0]["lineage_status"] == "newly_observed"


def test_nested_real_workspace_identity_is_not_lost_when_default_project_is_removed() -> None:
    subject, normalization = scan_assessment_subject(
        {
            "repository": "BoneManTGRM/NICO",
            "project_id": "default_project",
            "context": {"workspace_id": "workspace-7"},
        }
    )

    assert subject == {
        "repository": "bonemantgrm/nico",
        "workspace_id": "workspace-7",
    }
    assert normalization["ignored_optional_placeholders"] == {
        "project_id": "default_project"
    }
    assert normalization["identity_conflicts"] == {}
    assert normalization["identity_conflict_fail_closed"] is False


def test_conflicting_subject_identity_sources_fail_closed() -> None:
    subject, normalization = scan_assessment_subject(
        {
            "repository": "BoneManTGRM/NICO",
            "context": {"repository": "OtherOrg/OtherRepo"},
        }
    )

    assert subject == {}
    assert normalization["identity_conflict_fail_closed"] is True
    assert normalization["identity_conflicts"] == {
        "repository": ["bonemantgrm/nico", "otherorg/otherrepo"]
    }


def test_one_deduplicated_record_with_multiple_occurrences_is_not_fake_grouping() -> None:
    result = refine_candidate_review_workload(
        _register([_candidate("ONLY", occurrence_count=5)])
    )
    finding = result["findings"][0]
    metrics = result["technical_triage"]["workload_metrics"]

    assert finding["grouped_review_eligible"] is False
    assert metrics["candidates_requiring_individual_human_attention"] == 5
    assert metrics["individual_human_review_record_count"] == 1
    assert metrics["grouped_review_cluster_count"] == 0
    assert metrics["human_review_work_units"] == 1


def test_repetitive_lower_risk_static_candidates_become_one_grouped_work_unit() -> None:
    findings = [
        _candidate("A", path="nico/a.py", line=10),
        _candidate("B", path="nico/b.py", line=20),
        _candidate("C", path="nico/c.py", line=30),
    ]
    result = refine_candidate_review_workload(_register(findings))
    metrics = result["technical_triage"]["workload_metrics"]

    assert {item["candidate_id"] for item in result["findings"]} == {"A", "B", "C"}
    assert {item["technical_triage_verdict"] for item in result["findings"]} == {
        "needs_review"
    }
    assert len({item["cluster_id"] for item in result["findings"]}) == 1
    assert all(item["grouped_review_eligible"] is True for item in result["findings"])
    assert all(item["cluster_candidate_ids"] == ["A", "B", "C"] for item in result["findings"])
    assert metrics["human_attention_candidate_count_before_grouping"] == 3
    assert metrics["candidates_requiring_individual_human_attention"] == 0
    assert metrics["grouped_human_review_candidate_count"] == 3
    assert metrics["grouped_review_cluster_count"] == 1
    assert metrics["human_review_work_units"] == 1
    assert metrics["review_workload_reduction_count"] == 2
    assert result["technical_triage"]["workload_refinement"][
        "technical_verdicts_changed"
    ] is False


def test_dependency_grouping_requires_exact_package_version_ecosystem_and_advisory() -> None:
    same = ("urllib3", "2.2.1", "pypi", "PYSEC-2026-1")
    findings = [
        _candidate(
            "D1",
            category="dependency",
            scanner="osv-scanner",
            rule="PYSEC-2026-1",
            path="requirements.txt",
            dependency=same,
        ),
        _candidate(
            "D2",
            category="dependency",
            scanner="osv-scanner",
            rule="PYSEC-2026-1",
            path="requirements.txt",
            dependency=same,
        ),
        _candidate(
            "D3",
            category="dependency",
            scanner="osv-scanner",
            rule="PYSEC-2026-1",
            path="requirements.txt",
            dependency=("urllib3", "2.2.2", "pypi", "PYSEC-2026-1"),
        ),
    ]
    result = refine_candidate_review_workload(_register(findings))
    by_id = {item["candidate_id"]: item for item in result["findings"]}

    assert by_id["D1"]["cluster_id"] == by_id["D2"]["cluster_id"]
    assert by_id["D1"]["grouped_review_eligible"] is True
    assert by_id["D3"]["cluster_id"] != by_id["D1"]["cluster_id"]
    assert by_id["D3"]["grouped_review_eligible"] is False


def test_secrets_high_risk_changed_conflicting_and_count_only_candidates_stay_individual() -> None:
    findings = [
        _candidate("S1", category="secret", scanner="gitleaks", rule="token"),
        _candidate("S2", category="secret", scanner="gitleaks", rule="token"),
        _candidate("H1", severity="high"),
        _candidate("H2", severity="high"),
        _candidate("E1", evidence_changed=True),
        _candidate("E2", evidence_changed=True),
        _candidate("C1"),
        _candidate("C2"),
        _candidate("O1", evidence_quality="count_only"),
        _candidate("O2", evidence_quality="count_only"),
    ]
    findings[6]["deterministic_evidence"] = {"conflicting_evidence": True}
    findings[7]["deterministic_evidence"] = {"conflicting_evidence": True}
    result = refine_candidate_review_workload(_register(findings))
    metrics = result["technical_triage"]["workload_metrics"]

    assert all(item["grouped_review_eligible"] is False for item in result["findings"])
    assert metrics["candidates_requiring_individual_human_attention"] == len(findings)
    assert metrics["grouped_review_cluster_count"] == 0
    assert metrics["human_review_work_units"] == len(findings)


def test_refinement_is_deterministic_across_candidate_order() -> None:
    findings = [
        _candidate("A", path="nico/a.py", line=10),
        _candidate("B", path="nico/b.py", line=20),
        _candidate("C", path="nico/c.py", line=30),
    ]
    first = refine_candidate_review_workload(_register(findings))
    second = refine_candidate_review_workload(_register(list(reversed(findings))))
    first_by_id = {item["candidate_id"]: item["cluster_id"] for item in first["findings"]}
    second_by_id = {item["candidate_id"]: item["cluster_id"] for item in second["findings"]}

    assert first_by_id == second_by_id
    assert first["technical_triage"]["workload_metrics"] == second["technical_triage"]["workload_metrics"]


def test_historical_shape_reduces_human_work_without_creating_approval() -> None:
    stable = [
        _candidate(
            f"STABLE-{index}",
            verdict="not_actionable",
            confidence="high",
            proof_gaps=[],
            route="STABLE_CARRY_FORWARD",
            path=f"nico/stable_{index}.py",
        )
        for index in range(606)
    ]
    fresh_static = [
        _candidate(f"FRESH-{index}", path=f"nico/fresh_{index}.py")
        for index in range(23)
    ]
    secret = [_candidate("SECRET", category="secret", scanner="gitleaks", rule="token")]
    register = _register(stable + fresh_static + secret)
    register["technical_triage"]["fresh_technical_triage_completed"] = 24
    register["technical_triage"]["workload_metrics"]["stable_carry_forward_count"] = 606

    result = refine_candidate_review_workload(register)
    metrics = result["technical_triage"]["workload_metrics"]

    assert metrics["total_candidates"] == 630
    assert metrics["candidates_requiring_individual_human_attention"] == 1
    assert metrics["grouped_review_cluster_count"] == 1
    assert metrics["human_review_work_units"] == 2
    assert metrics["automated_not_actionable_candidate_count"] == 606
    assert metrics["human_attention_candidate_count_before_grouping"] == 24
    assert metrics["end_to_end_review_workload_reduction_count"] == 628
    assert metrics["end_to_end_review_workload_reduction_pct"] == 99.68
    assert metrics["quality_control_sample_pool"] == 606
    assert metrics["quality_control_sample_record_count"] == 606
    boundaries = result["technical_triage"]["workload_refinement"]
    assert boundaries["human_disposition_created"] is False
    assert boundaries["human_approval_created"] is False
    assert boundaries["client_delivery_allowed"] is False
    assert boundaries["score_effect"] == "none"


def test_current_exact_source_harness_triage_is_quality_control_eligible_after_change() -> None:
    candidate = _candidate(
        "CURRENT-B101",
        path="scripts/mobile_restart_live_acceptance_v1.py",
        rule="B101",
        severity="low",
        verdict="not_actionable",
        confidence="high",
        proof_gaps=[],
        route="QUALITY_CONTROL_ELIGIBLE",
        evidence_changed=True,
    )
    candidate["technical_triage_source"] = "fresh_deterministic_contextual_analysis"
    candidate["technical_triage_rationale_code"] = (
        "assert_nonproduction_validation_harness"
    )

    result = refine_candidate_review_workload(_register([candidate]))
    metrics = result["technical_triage"]["workload_metrics"]

    assert metrics["human_review_work_units"] == 0
    assert metrics["quality_control_sample_pool"] == 1
    assert metrics["quality_control_sample_record_count"] == 1


def test_review_gate_pdf_says_technical_triage_complete_and_human_disposition_pending() -> None:
    metrics = {
        "total_candidates": 630,
        "technical_triage_completed": 630,
        "technical_triage_coverage_pct": 100.0,
        "stable_carry_forward_count": 606,
        "candidates_requiring_individual_human_attention": 7,
        "grouped_human_review_candidate_count": 17,
        "grouped_review_cluster_count": 3,
        "human_review_work_units": 10,
        "quality_control_sample_pool": 606,
        "automated_not_actionable_candidate_count": 606,
        "human_attention_candidate_count_before_grouping": 24,
        "end_to_end_review_workload_reduction_count": 620,
        "end_to_end_review_workload_reduction_pct": 98.41,
    }
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_test",
        },
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 89,
        },
        "scanner_execution_records": [
            {"completed": True, "scanner_name": f"scanner-{index}"}
            for index in range(9)
        ],
        "review_candidate_summary": {
            "review_required_total": 630,
            "verified_material_total": 0,
            "by_category": {
                "dependency": {"raw": 20, "material": 0, "review_required": 20},
                "secret": {"raw": 17, "material": 0, "review_required": 17},
                "static": {"raw": 593, "material": 0, "review_required": 593},
            },
        },
        "technical_triage": {
            "status": "complete",
            "fresh_technical_triage_completed": 24,
            "workload_metrics": metrics,
        },
    }
    pdf = render_phase1_evidence_review_gate_pdf(
        canonical,
        {"summary": {"exact_source_code_finding_count": 50}},
        spanish=False,
    )
    text = " ".join(
        " ".join((page.extract_text() or "").split())
        for page in PdfReader(io.BytesIO(pdf)).pages
    )

    assert "automated technical triage" in text.lower()
    assert "human dispositions remain pending" in text.lower()
    assert "scanner-candidate review work units" in text.lower()
    assert "grouped human-review clusters" in text.lower()
    assert "canonical pending dispositions are not the active operator queue" in text.lower()
    assert "raw-to-work-unit reduction" in text.lower()
    assert "620 (98.41%)" in text
    assert "until triaged" not in text.lower()
    assert (
        "Only an authorized human reviewer may approve the exact immutable artifacts."
        in text
    )
    assert "Client delivery requires a separate authorized action." in text
    assert "APPROVED FINAL and CLIENT DELIVERY AUTHORIZED" not in text


def test_zero_scanner_queue_and_one_exact_source_finding_render_as_one_total_review_unit() -> None:
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/SARA",
            "commit_sha": "a" * 40,
            "run_id": "comprun_zero_scanner_one_exact_source",
        },
        "assessment": {"technical_score": 93, "evidence_adjusted_score": 93},
        "scanner_execution_records": [],
        "review_candidate_summary": {
            "review_required_total": 0,
            "verified_material_total": 0,
            "by_category": {},
        },
        "technical_triage": {
            "status": "complete",
            "fresh_technical_triage_completed": 0,
            "workload_metrics": {
                "total_candidates": 0,
                "technical_triage_completed": 0,
                "technical_triage_coverage_pct": 100.0,
                "human_review_work_units": 0,
            },
        },
    }
    finding_register = {
        "code_findings": [
            {
                "finding_id": "RISK-P1-COMPLEXITY",
                "status": "needs_review",
                "path": "src/revenue-pilot.ts",
                "line": 331,
                "title": "Reduce complexity in completeRevenuePilotRole",
            }
        ],
        "operational_findings": [],
        "summary": {"exact_source_code_finding_count": 1},
    }
    canonical["client_finding_remediation_register"] = finding_register

    english = workload_markdown(canonical, spanish=False)
    spanish = workload_markdown(canonical, spanish=True)
    pdf = render_phase1_evidence_review_gate_pdf(
        canonical, finding_register, spanish=False
    )
    pdf_text = " ".join(
        " ".join((page.extract_text() or "").split())
        for page in PdfReader(io.BytesIO(pdf)).pages
    )

    assert "Scanner-candidate review work units: 0" in english
    assert "Exact-source review work units: 1" in english
    assert "Operational/context review work units: 0" in english
    assert "Total unresolved human-review work units: 1" in english
    assert "Unidades de trabajo de revisión de candidatos de analizadores: 0" in spanish
    assert "Unidades de revisión con fuente exacta: 1" in spanish
    assert "Unidades de revisión operativa o contextual: 0" in spanish
    assert "Total de unidades de revisión humana sin resolver: 1" in spanish
    assert "Scanner-candidate review work units" in pdf_text
    assert "Exact-source review work units" in pdf_text
    assert "Operational/context review work units" in pdf_text
    assert "Total unresolved human-review work units" in pdf_text
    assert "0 verified findings" not in english.casefold()


def test_workload_markdown_reads_scanner_units_from_nested_canonical_register() -> None:
    canonical = {
        "assessment": {
            "canonical_scanner_finding_register": {
                "technical_triage": {
                    "human_review_work_units": 7,
                    "workload_metrics": {
                        "total_candidates": 11,
                        "technical_triage_completed": 11,
                        "technical_triage_coverage_pct": 100.0,
                    },
                }
            },
            "client_finding_remediation_register": {
                "code_findings": [],
                "operational_findings": [],
            },
        }
    }

    english = workload_markdown(canonical, spanish=False)

    assert "Scanner-candidate review work units: 7" in english
    assert "Exact-source review work units: 0" in english
    assert "Operational/context review work units: 0" in english
    assert "Total unresolved human-review work units: 7" in english


def test_scanner_derived_findings_are_not_double_counted_as_supplemental_work() -> None:
    canonical = {
        "assessment": {
            "canonical_scanner_finding_register": {
                "technical_triage": {"human_review_work_units": 1},
            },
            "client_finding_remediation_register": {
                "code_findings": [
                    {
                        "finding_id": "SCANNER-B101",
                        "status": "review_required",
                        "path": "src/service.py",
                        "line": 20,
                        "record_source": "scanner_finding",
                    }
                ],
                "operational_findings": [
                    {
                        "finding_id": "SCANNER-CONFIG",
                        "status": "review_required",
                        "title": "Scanner configuration requires review",
                        "record_source": "scanner_finding",
                    }
                ],
            },
        }
    }

    from nico.review_workload_truth_v1 import review_workload_summary

    workload = review_workload_summary(canonical)

    assert workload["scanner_candidate_review_work_units"] == 1
    assert workload["exact_source_review_work_units"] == 0
    assert workload["operational_context_review_work_units"] == 0
    assert workload["total_unresolved_human_review_work_units"] == 1


def test_spanish_phase1_review_gate_is_laid_out_from_spanish_copy() -> None:
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_test",
        },
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 89,
        },
        "scanner_execution_records": [],
        "review_candidate_summary": {
            "review_required_total": 1,
            "verified_material_total": 0,
            "by_category": {
                "dependency": {"raw": 1, "material": 0, "review_required": 1}
            },
        },
        "technical_triage": {
            "status": "complete",
            "workload_metrics": {
                "total_candidates": 0,
                "technical_triage_completed": 0,
                "technical_triage_coverage_pct": 0,
            },
        },
    }
    pdf = render_phase1_evidence_review_gate_pdf(
        canonical,
        {"summary": {"exact_source_code_finding_count": 0}},
        spanish=True,
    )
    text = " ".join(
        " ".join((page.extract_text() or "").split())
        for page in PdfReader(io.BytesIO(pdf)).pages
    )

    for expected in (
        "Campo",
        "Valor",
        "El triaje técnico y la disposición humana están separados",
        "Métrica de carga del revisor",
        "Límite del paquete del cliente",
        "permanecen en JSON y CSV canónicos",
        "Dependencias",
        "Solo un revisor humano autorizado puede aprobar los artefactos inmutables exactos.",
        "La entrega al cliente requiere una acción autorizada independiente.",
    ):
        assert expected in text
    for forbidden in (
        "Field",
        "Reviewer workload metric",
        "Client package boundary",
        "Full candidate evidence",
        "Dependency",
        "FINAL APROBADO y ENTREGA AUTORIZADA",
    ):
        assert forbidden not in text
