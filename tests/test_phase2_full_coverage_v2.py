from __future__ import annotations

import base64
import io
import zipfile
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from nico.comprehensive_delivery_package_v2 import build_comprehensive_delivery_package
from nico.comprehensive_review_decision_v1 import build_reviewed_edition
from nico.comprehensive_review_report_truth_v1 import synchronize_review_truth
from nico.comprehensive_review_work_v2 import (
    apply_review_work_action,
    assert_ready_for_approval,
    review_work_projection,
)


def _candidate(
    candidate_id: str,
    cluster_id: str,
    *,
    severity: str = "low",
    verdict: str = "not_actionable",
    confidence: float = 0.97,
    grouped: bool = True,
    change: str = "unchanged",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "finding_id": f"finding-{candidate_id}",
        "cluster_id": cluster_id,
        "severity": severity,
        "scanner": "semgrep" if candidate_id != "B" else "dependency",
        "category": "security",
        "rule": f"rule-{candidate_id}",
        "advisory": f"ADV-{candidate_id}",
        "path": f"src/{candidate_id.lower()}.py",
        "package": "fixture-package",
        "technical_triage_verdict": verdict,
        "technical_triage_confidence": confidence,
        "evidence_change_state": change,
        "grouped_review_eligible": grouped,
        "review_requires_individual_attention": not grouped,
        "homogeneous_evidence": True,
        "homogeneous_verdict": True,
        "review_routing_class": "CRITICAL_ATTENTION" if severity == "high" else "AUTOMATED_TRIAGE_COMPLETE",
        "human_disposition": None,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _register() -> dict:
    findings = [
        _candidate("A", "GROUP"),
        _candidate("B", "GROUP"),
        _candidate("C", "C", severity="high", verdict="confirmed", confidence=0.99, grouped=False, change="new"),
    ]
    return {
        "artifact_schema": "nico.canonical_scanner_finding_register.v1",
        "candidate_record_count": 3,
        "findings": findings,
        "review_workload_clusters": [
            {
                "cluster_id": "GROUP",
                "candidate_ids": ["A", "B"],
                "candidate_record_count": 2,
                "cluster_size": 2,
                "representative_candidate_id": "A",
                "grouped_review_eligible": True,
                "grouped_human_review_cluster": True,
                "homogeneous_evidence": True,
                "homogeneous_verdict": True,
                "underlying_candidate_disposition_required": True,
            },
            {
                "cluster_id": "C",
                "candidate_ids": ["C"],
                "candidate_record_count": 1,
                "cluster_size": 1,
                "representative_candidate_id": "C",
                "grouped_review_eligible": False,
                "grouped_human_review_cluster": False,
                "homogeneous_evidence": True,
                "homogeneous_verdict": True,
                "underlying_candidate_disposition_required": True,
            },
        ],
        "technical_triage": {"total_candidates": 3},
    }


def _minimal_pdf() -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(72, 720, "NICO Comprehensive canonical report fixture")
    pdf.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _record() -> dict:
    identity = {
        "run_id": "comprun_phase2_v2",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_phase2_v2",
        "customer_id": "customer_v2",
        "project_id": "project_v2",
        "assessment_depth": "comprehensive",
        "report_language": "en",
    }
    canonical = {
        "identity": {
            key: identity[key]
            for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
        },
        "assessment": {"canonical_scanner_finding_register": _register()},
        "findings_register": [],
        "roadmap": [],
        "staffing_plan": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package = {
        "report_id": "report_phase2_v2",
        "markdown": "# NICO Comprehensive\n\nDRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n",
        "html": "<html><body><main><article><h1>NICO Comprehensive</h1><p>PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED</p></article></main></body></html>",
        "pdf_base64": _minimal_pdf(),
        "pdf_page_count": 1,
        "json": canonical,
        "canonical_truth_sha256": "evidence-hash-fixture",
        "findings_csv": "finding_id,title\nfixture,Fixture\n",
        "evidence_csv": "evidence_id,source\nev-1,scanner\n",
        "jira_csv": "summary,description\nFixture,Backlog fixture\n",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return {
        "identity": identity,
        "status": "review_required",
        "terminal": True,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_results": {
            "immutable_repository_snapshot": {"snapshot": {"tree_sha": "b" * 40}},
            "deep_scanner_triage": {"scanner_run_id": "scan-phase2-v2"},
            "final_comprehensive_report_generation": {"report_package": package},
        },
    }


def _human(action: str, reviewer: str = "Alice", role: str = "Security specialist", **extra) -> dict:
    return {
        "action": action,
        "reviewer": reviewer,
        "reviewer_role": role,
        "review_authorized": True,
        "authorization_confirmed": True,
        **extra,
    }


def _with_ledger(record: dict, ledger: dict) -> dict:
    updated = deepcopy(record)
    updated["review_work_ledger"] = deepcopy(ledger)
    return updated


def _complete_review(record: dict) -> dict:
    ledger = apply_review_work_action(
        record,
        _human(
            "configure_qc_sampling",
            reviewer="Alice",
            sampling_strategy="risk_weighted",
            sample_size=2,
        ),
        now=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )
    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "disposition_group",
            cluster_id="GROUP",
            disposition="false_positive",
            rationale="Exact retained evidence shows the homogeneous group is non-actionable.",
        ),
        now=datetime(2026, 8, 11, 12, 5, tzinfo=UTC),
    )
    record = _with_ledger(record, ledger)
    ledger = apply_review_work_action(
        record,
        _human(
            "disposition_candidate",
            candidate_id="C",
            disposition="confirmed",
            rationale="Exact retained evidence confirms the high-impact condition.",
            residual_risk="Material risk remains until remediation is verified.",
            residual_risk_owner="Security owner",
            escalation_resolution="Confirmed and escalated to the security owner for remediation.",
            escalation_owner="Security owner",
        ),
        now=datetime(2026, 8, 11, 12, 10, tzinfo=UTC),
    )
    record = _with_ledger(record, ledger)
    for candidate_id in ("A", "B"):
        ledger = apply_review_work_action(
            record,
            _human(
                "quality_control",
                reviewer="Bob",
                role="Independent quality reviewer",
                candidate_id=candidate_id,
                qc_outcome="agree",
                qc_note=f"Independent QC agrees with {candidate_id} disposition.",
            ),
            now=datetime(2026, 8, 11, 12, 15, tzinfo=UTC),
        )
        record = _with_ledger(record, ledger)
    return record


def test_six_review_queues_and_workload_metrics_are_projected() -> None:
    projection = review_work_projection(_record())
    assert projection["queue_counts"]["critical_material"] == 1
    assert projection["queue_counts"]["stable_carry_forward"] == 2
    assert projection["queue_counts"]["quality_control_sample"] == 1
    assert projection["queue_counts"]["human_disposition_completed"] == 0
    assert projection["workload_metrics"]["individual_attention_count"] == 1
    assert projection["workload_metrics"]["grouped_review_eligible_count"] == 2
    assert projection["workload_metrics"]["four_hour_target_is_safety_gate"] is False


def test_configurable_risk_weighted_sampling_never_dispositions_candidates() -> None:
    record = _record()
    ledger = apply_review_work_action(
        record,
        _human("configure_qc_sampling", sampling_strategy="risk_weighted", sample_size=2),
        now=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )
    sampling = ledger["quality_control_sampling"]
    assert sampling["sampling_strategy"] == "risk_weighted"
    assert sampling["sampling_version"] == "nico.phase2.qc_sampling.v2"
    assert sampling["population_candidate_ids"] == ["A", "B"]
    assert sampling["selected_candidate_ids"] == ["A", "B"]
    assert ledger["dispositions"] == {}
    projection = review_work_projection(_with_ledger(record, ledger))
    assert projection["remaining_candidate_count"] == 3
    assert projection["ready_for_final_approval"] is False


def test_review_can_finish_without_empirical_four_hour_study_becoming_safety_gate() -> None:
    record = _complete_review(_record())
    projection = assert_ready_for_approval(record)
    assert projection["ready_for_final_approval"] is True
    assert projection["empirical_measurement"]["status"] == "not_yet_measured"
    assert projection["workload_metrics"]["four_hour_target_is_safety_gate"] is False
    assert projection["queue_counts"]["human_disposition_completed"] == 3


def test_changed_canonical_evidence_invalidates_stale_human_review_state() -> None:
    record = _record()
    ledger = apply_review_work_action(
        record,
        _human("configure_qc_sampling", sampling_strategy="deterministic", sample_size=1),
        now=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )
    record = _with_ledger(record, ledger)
    mutated = deepcopy(record)
    findings = mutated["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"]["assessment"]["canonical_scanner_finding_register"]["findings"]
    findings[0]["path"] = "src/changed-after-review.py"
    with pytest.raises(ValueError, match="review_work_source_evidence_changed"):
        review_work_projection(mutated)


def test_review_truth_is_synchronized_across_json_markdown_html_pdf_and_csv() -> None:
    record = _complete_review(_record())
    synchronized = synchronize_review_truth(record)
    package = synchronized["stage_results"]["final_comprehensive_report_generation"]["report_package"]
    truth = package["human_review_truth"]
    assert truth["raw_scanner_candidates"] == 3
    assert truth["technical_triage_completed"] == 3
    assert truth["authorized_human_disposition_pending"] == 0
    assert truth["authorized_human_disposition_completed"] == 3
    assert truth["confirmed_material_findings"] == 1
    assert truth["final_human_approval_status"] == "pending"
    assert truth["client_delivery_authorization_status"] == "blocked"
    assert "Human Review and Approval Truth" in package["markdown"]
    assert "Authorized human disposition completed" in package["html"]
    assert package["json"]["human_review_truth"]["confirmed_material_findings"] == 1
    assert "human_dispositions_completed" in package["findings_csv"]
    assert "candidate_id,cluster_id" in package["candidate_register_csv"]
    pdf = base64.b64decode(package["pdf_base64"], validate=True)
    assert pdf.startswith(b"%PDF")
    assert package["pdf_page_count"] == 2


def test_final_approval_certificate_binds_exact_review_ledger() -> None:
    record = synchronize_review_truth(_complete_review(_record()))
    manifest = build_reviewed_edition(
        record,
        reviewer="Alice",
        reviewer_role="Security specialist",
        decision="approved",
        decision_reason="All candidate dispositions, independent QC, evidence, and escalation gates are complete.",
        decided_at="2026-08-11T13:00:00+00:00",
    )
    assert manifest["accepted_edition"] is True
    assert manifest["review_work_ledger_sha256"]
    assert manifest["review"]["review_work_ledger_sha256"] == manifest["review_work_ledger_sha256"]
    assert manifest["review_work_source_sha256"] == record["review_work_ledger"]["review_source_sha256"]


def test_approved_delivery_contains_exactly_one_client_pdf() -> None:
    record = synchronize_review_truth(_complete_review(_record()))
    package = deepcopy(record["stage_results"]["final_comprehensive_report_generation"]["report_package"])
    package["accepted_edition"] = {
        "accepted_edition": True,
        "client_delivery_allowed": True,
        "review": {"decision": "approved"},
    }
    delivery = build_comprehensive_delivery_package(package)
    assert delivery["status"] == "approved_for_delivery"
    assert delivery["one_client_report"] is True
    assert delivery["client_pdf_count"] == 1
    archive = base64.b64decode(delivery["zip_base64"], validate=True)
    with zipfile.ZipFile(io.BytesIO(archive), "r") as zipped:
        pdfs = [name for name in zipped.namelist() if name.endswith(".pdf")]
    assert pdfs == ["01_nico_comprehensive_report.pdf"]
    assert "strategic" not in delivery["filename"].casefold()
    assert "premium" not in delivery["filename"].casefold()
