from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

VERSION = "nico.canonical_strategic_package.v1"

TECHNICAL_MODULES: tuple[tuple[str, str], ...] = (
    ("code_audit", "Code quality and maintainability"),
    ("dependency_health", "Dependency and library ecosystem"),
    ("secrets_review", "Secrets and credential hygiene"),
    ("static_analysis", "Static analysis and type safety"),
    ("ci_cd", "CI/CD and classified release reliability"),
    ("architecture_debt", "Architecture and technical debt"),
    ("velocity_complexity", "Delivery velocity and change risk"),
    ("test_strategy", "Test strategy and measured coverage"),
    ("runtime_operations", "Runtime and operational readiness"),
    ("security_architecture", "Security architecture and trust boundaries"),
    ("privacy_data", "Privacy and data handling"),
    ("performance_scalability", "Performance and scalability"),
    ("documentation_dx", "Documentation and developer experience"),
)

STRATEGIC_MODULES: tuple[tuple[str, str], ...] = (
    ("functional_qa", "Functional QA plan and observed results"),
    ("platform_parity", "Browser, device, and platform parity"),
    ("accessibility_ux", "Accessibility and UX friction"),
    ("stakeholder_context", "Stakeholder objectives and constraints"),
    ("business_consequences", "Business consequences of technical findings"),
    ("risk_register", "Decision-grade risk register"),
    ("quick_wins", "Prioritized quick wins"),
    ("roadmap_30_60_90", "30/60/90-day execution plan"),
    ("six_month_roadmap", "Six-month roadmap"),
    ("resourcing", "Resourcing and capacity plan"),
    ("cost_of_delay", "Cost-of-delay and effort estimates"),
    ("decision_log", "Decision log and unresolved questions"),
)

ARTIFACT_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("executive_decision_report_pdf", "01_executive_decision_report.pdf"),
    ("detailed_technical_assessment_pdf", "02_detailed_technical_assessment.pdf"),
    ("evidence_appendix_pdf", "03_evidence_appendix.pdf"),
    ("findings_register_csv", "04_findings_register.csv"),
    ("findings_register_json", "05_findings_register.json"),
    ("remediation_backlog_csv", "06_remediation_backlog.csv"),
    ("risk_register_csv", "07_risk_register.csv"),
    ("roadmap_30_60_90_csv", "08_roadmap_30_60_90.csv"),
    ("six_month_roadmap_csv", "09_six_month_roadmap.csv"),
    ("resourcing_plan_csv", "10_resourcing_plan.csv"),
    ("evidence_manifest_json", "11_evidence_manifest.json"),
    ("score_assurance_ledger_json", "12_score_and_assurance_ledger.json"),
    ("sbom_json", "13_sbom.json"),
    ("ci_run_classification_json", "14_ci_run_classification.json"),
    ("approval_record_json", "15_approval_record.json"),
    ("executive_review_slides", "16_executive_review_slides.pdf"),
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: max(0, limit - 3)].rstrip() + "..."


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    raw = value if isinstance(value, bytes) else _canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _first(*values: Any, limit: int = 300) -> str:
    for value in values:
        candidate = _text(value, limit)
        if candidate:
            return candidate
    return ""


def _safe_identifier(value: Any, *, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", _text(value, 180)).strip("-.")
    return normalized or fallback


def _assessment(payload: dict[str, Any]) -> dict[str, Any]:
    direct = _record(payload.get("assessment"))
    if direct:
        return direct
    report_package = _record(payload.get("report_package"))
    package_json = _record(report_package.get("json"))
    nested = _record(package_json.get("assessment"))
    if nested:
        return nested
    if isinstance(payload.get("sections"), list):
        return {
            "sections": _records(payload.get("sections")),
            "findings_register": _records(payload.get("findings_register")),
            "maturity_signal": _record(payload.get("maturity_signal")),
        }
    return {}


def _scanner(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("scanner", "scanner_run", "scanner_evidence", "scanner_worker"):
        candidate = _record(payload.get(key))
        if candidate:
            return candidate
    return {}


def _snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return _record(payload.get("repository_snapshot") or payload.get("snapshot"))


def _reports(payload: dict[str, Any]) -> dict[str, Any]:
    reports = _record(payload.get("reports"))
    if reports:
        return reports
    package = _record(payload.get("report_package"))
    return package


def _evidence_bundle_hash(payload: dict[str, Any]) -> str:
    bundle = _record(payload.get("evidence_artifact_bundle") or payload.get("evidence_bundle"))
    return _first(bundle.get("bundle_hash"), bundle.get("sha256"), payload.get("evidence_bundle_hash"), limit=128)


def _report_digest(payload: dict[str, Any]) -> str:
    reports = _reports(payload)
    return _first(
        reports.get("pdf_sha256"),
        reports.get("canonical_truth_sha256"),
        reports.get("report_artifact_digest"),
        payload.get("canonical_truth_sha256"),
        limit=128,
    )


def _section_ledger(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for index, section in enumerate(_records(assessment.get("sections")), start=1):
        section_id = _safe_identifier(section.get("id"), fallback=f"section-{index}")
        score = section.get("presented_score")
        if not isinstance(score, (int, float)):
            score = section.get("score_value") if isinstance(section.get("score_value"), (int, float)) else None
        findings = [
            _text(item, 520) if not isinstance(item, dict) else _text(item.get("title") or item.get("message"), 520)
            for item in (section.get("findings") or [])
            if _text(item if not isinstance(item, dict) else item.get("title") or item.get("message"), 520)
        ]
        unavailable = [_text(item, 520) for item in (section.get("unavailable") or []) if _text(item, 520)]
        evidence = [_text(item, 700) for item in (section.get("evidence") or []) if _text(item, 700)]
        assurance = _first(section.get("assurance_label"), section.get("evidence_assurance"), section.get("assurance_status"), limit=80) or "UNAVAILABLE"
        risk = _first(section.get("risk_disposition"), section.get("risk_status"), section.get("status"), limit=80) or "REVIEW REQUIRED"
        ledger.append(
            {
                "control_id": section_id,
                "label": _first(section.get("label"), section.get("title"), section_id, limit=220),
                "technical_score": int(score) if isinstance(score, (int, float)) else None,
                "technical_band": _first(section.get("score_band_label"), section.get("score_band"), limit=80) or "NOT SCORED",
                "evidence_assurance": assurance.upper(),
                "risk_disposition": risk.upper(),
                "included_in_maturity": section.get("exclude_from_maturity") is not True and score is not None,
                "evidence": evidence,
                "confirmed_or_retained_findings": findings,
                "unavailable_evidence": unavailable,
                "verified_green_exit_criteria": _first(
                    section.get("verified_green_exit_criteria"),
                    section.get("exit_criteria"),
                    section.get("acceptance_criteria"),
                    "Technical score is at least 80, evidence assurance is VERIFIED, risk disposition is GREEN, and every retained finding has a traceable disposition.",
                    limit=900,
                ),
            }
        )
    return ledger


def _module_statuses(payload: dict[str, Any], assessment: dict[str, Any], depth: str) -> list[dict[str, Any]]:
    section_by_id = {str(item.get("id") or ""): item for item in _records(assessment.get("sections"))}
    output: list[dict[str, Any]] = []
    for module_id, label in TECHNICAL_MODULES:
        section = _record(section_by_id.get(module_id))
        status = "complete" if section else "not_assessed"
        output.append(
            {
                "module_id": module_id,
                "label": label,
                "status": status,
                "source": "canonical_technical_scorecard" if section else "no_canonical_section_returned",
                "human_evidence_required": False,
            }
        )

    strategic_sources = {
        "functional_qa": payload.get("functional_qa") or payload.get("qa_results"),
        "platform_parity": payload.get("platform_parity") or payload.get("parity_matrix"),
        "accessibility_ux": payload.get("accessibility_review") or payload.get("ux_review"),
        "stakeholder_context": payload.get("stakeholder_context") or payload.get("stakeholder_discovery"),
        "business_consequences": assessment.get("business_consequences") or payload.get("business_consequences"),
        "risk_register": assessment.get("executive_risk_register") or payload.get("risk_register"),
        "quick_wins": payload.get("quick_wins") or assessment.get("quick_wins"),
        "roadmap_30_60_90": payload.get("roadmap_30_60_90") or assessment.get("roadmap_30_60_90"),
        "six_month_roadmap": payload.get("roadmap") or payload.get("six_month_roadmap"),
        "resourcing": payload.get("staffing_plan") or payload.get("resourcing_plan"),
        "cost_of_delay": payload.get("cost_of_delay") or assessment.get("cost_of_delay"),
        "decision_log": payload.get("decision_log") or assessment.get("decision_log"),
    }
    for module_id, label in STRATEGIC_MODULES:
        source = strategic_sources.get(module_id)
        complete = bool(source)
        output.append(
            {
                "module_id": module_id,
                "label": label,
                "status": "complete" if complete else ("not_assessed" if depth == "strategic" else "not_in_core_scope"),
                "source": "retained_evidence" if complete else "explicit_human_or_extended_evidence_not_retained",
                "human_evidence_required": module_id in {"functional_qa", "platform_parity", "accessibility_ux", "stakeholder_context", "decision_log"},
            }
        )
    return output


def _finding_location(record: dict[str, Any]) -> str:
    return _first(record.get("location"), record.get("file_path"), record.get("path"), limit=360) or "Exact location not retained"


def _affected_files(location: str) -> list[str]:
    if not location or location == "Exact location not retained":
        return []
    candidate = location.split(";", 1)[0].split(":", 1)[0].strip()
    return [candidate] if "/" in candidate or "." in candidate else []


def _verification_tests(category: str, record: dict[str, Any]) -> list[str]:
    origin = _first(record.get("tool"), record.get("scanner"), limit=80)
    tests = ["Run the repository's relevant unit and integration test suites."]
    if origin:
        tests.append(f"Rerun {origin} against the same immutable commit lineage after the repair.")
    if category == "ci_cd":
        tests.append("Run the affected workflow twice and classify every non-success outcome by cause.")
    elif category == "architecture":
        tests.append("Add characterization tests before decomposition and verify behavior after the refactor.")
    elif category == "secret":
        tests.append("Verify credential rotation and run full-history secret scans without exposing raw credential material.")
    elif category == "dependency":
        tests.append("Regenerate the lockfile and run all dependency analyzers on the repaired exact SHA.")
    else:
        tests.append("Run the originating analyzer and retain the exact finding disposition.")
    return tests


def build_code_remediation_plan(payload: dict[str, Any]) -> dict[str, Any]:
    assessment = _assessment(payload)
    findings = _records(assessment.get("findings_register") or payload.get("findings_register"))
    items: list[dict[str, Any]] = []
    for index, finding in enumerate(findings, start=1):
        category = _first(finding.get("category"), "evidence", limit=60).casefold()
        location = _finding_location(finding)
        confidence = _first(finding.get("confidence"), "moderate", limit=40).casefold()
        exact_location = bool(_affected_files(location)) and "not retained" not in location.casefold()
        patch_confidence = "medium" if exact_location and confidence in {"high", "verified"} else "low"
        auto_patch_eligible = bool(
            exact_location
            and patch_confidence == "medium"
            and category in {"static", "dependency", "code", "ci_cd"}
            and _first(finding.get("recommendation"), limit=700)
        )
        finding_id = _safe_identifier(finding.get("id"), fallback=f"finding-{index}")
        recommendation = _first(
            finding.get("recommendation"),
            "Inspect the exact location, implement the smallest bounded repair, add regression coverage, and rerun the originating evidence source.",
            limit=900,
        )
        acceptance = _first(
            finding.get("acceptance_criteria"),
            "The repaired exact SHA passes the relevant tests and analyzers, and the finding is resolved or explicitly accepted with a named reviewer and expiry.",
            limit=900,
        )
        items.append(
            {
                "finding_id": finding_id,
                "priority": _first(finding.get("priority"), "P2", limit=20),
                "category": category,
                "title": _first(finding.get("title"), "Retained finding requires remediation", limit=360),
                "confidence": confidence,
                "exact_location": location,
                "affected_files": _affected_files(location),
                "source_evidence": _first(finding.get("evidence"), limit=1000),
                "technical_consequence": _first(finding.get("impact"), limit=900),
                "business_consequence": _first(
                    finding.get("business_consequence"),
                    "Unresolved technical risk can increase failure probability, delivery delay, support cost, or security exposure; the exact commercial impact requires project-specific evidence.",
                    limit=900,
                ),
                "recommended_change": recommendation,
                "implementation_steps": [
                    "Confirm the finding against the exact immutable commit and retained evidence.",
                    "Add or update characterization and regression tests before modifying behavior.",
                    recommendation,
                    "Rerun the relevant analyzer and the full affected test boundary.",
                    "Record the disposition, reviewer, exact repaired SHA, and verification evidence.",
                ],
                "owner_role": _first(finding.get("owner_role"), "Senior Product Engineer", limit=140),
                "effort_range": _first(finding.get("effort"), "Requires engineering estimate", limit=80),
                "dependencies_or_blockers": _first(finding.get("dependencies"), "Confirm exact location, reproduction, and affected test boundary.", limit=700),
                "regression_risk": "High" if category in {"architecture", "security_architecture", "database"} else "Moderate",
                "verification_tests": _verification_tests(category, finding),
                "rollback_plan": "Keep the repair isolated in a reviewable pull request; revert the repair commit if acceptance tests, production checks, or monitored behavior regress.",
                "exit_criteria": acceptance,
                "patch_confidence": patch_confidence,
                "auto_patch_eligible": auto_patch_eligible,
                "proposed_diff": "",
                "proposed_diff_status": "requires_exact_source_review" if exact_location else "blocked_missing_exact_location",
                "requires_human_engineering_review": True,
            }
        )
    return {
        "artifact_schema": VERSION,
        "status": "complete" if findings else "not_applicable",
        "finding_count": len(findings),
        "remediation_item_count": len(items),
        "automatic_code_change_performed": False,
        "items": items,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _risk_register(payload: dict[str, Any]) -> list[dict[str, Any]]:
    assessment = _assessment(payload)
    candidates = _records(assessment.get("executive_risk_register") or payload.get("executive_risk_register"))
    if candidates:
        return candidates
    output: list[dict[str, Any]] = []
    for item in _records(assessment.get("findings_register") or payload.get("findings_register"))[:12]:
        output.append(
            {
                "risk_id": _safe_identifier(item.get("id"), fallback=f"risk-{len(output) + 1}"),
                "title": _first(item.get("title"), "Retained technical risk", limit=360),
                "category": _first(item.get("category"), "technical", limit=80),
                "probability": "Requires project-specific review",
                "impact": _first(item.get("impact"), "Impact requires project-specific review.", limit=700),
                "priority": _first(item.get("priority"), "P2", limit=20),
                "owner": _first(item.get("owner_role"), "Engineering owner to be assigned", limit=140),
                "mitigation": _first(item.get("recommendation"), "Disposition and remediate the retained finding.", limit=700),
                "evidence": _first(item.get("evidence"), limit=700),
            }
        )
    return output


def _csv(rows: Iterable[dict[str, Any]], fields: tuple[str, ...]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _text(row.get(field), 4000) for field in fields})
    return buffer.getvalue()


def _artifact_statuses(payload: dict[str, Any], depth: str) -> list[dict[str, Any]]:
    reports = _reports(payload)
    existing = {
        "executive_decision_report_pdf": bool(reports.get("pdf_base64") or reports.get("pdf")),
        "detailed_technical_assessment_pdf": bool(reports.get("pdf_base64") or reports.get("pdf")),
        "evidence_appendix_pdf": bool(reports.get("evidence_appendix_pdf_base64") or reports.get("pdf_base64")),
        "findings_register_csv": bool(reports.get("findings_csv")),
        "findings_register_json": bool(_records(_assessment(payload).get("findings_register"))),
        "remediation_backlog_csv": bool(reports.get("remediation_backlog_csv")),
        "risk_register_csv": bool(reports.get("risk_register_csv")),
        "roadmap_30_60_90_csv": bool(reports.get("roadmap_30_60_90_csv")),
        "six_month_roadmap_csv": bool(reports.get("six_month_roadmap_csv")),
        "resourcing_plan_csv": bool(reports.get("resourcing_plan_csv")),
        "evidence_manifest_json": bool(reports.get("evidence_manifest_json")),
        "score_assurance_ledger_json": bool(reports.get("score_assurance_ledger_json")),
        "sbom_json": bool(reports.get("sbom_json") or payload.get("sbom")),
        "ci_run_classification_json": bool(reports.get("ci_run_classification_json") or payload.get("ci_run_classification")),
        "approval_record_json": bool(reports.get("approval_record_json") or payload.get("approval")),
        "executive_review_slides": bool(reports.get("executive_review_slides")),
    }
    return [
        {
            "artifact_id": artifact_id,
            "filename": filename,
            "status": "ready" if existing.get(artifact_id) else ("planned" if depth == "strategic" else "not_in_core_scope"),
            "required_for_final_accepted": artifact_id not in {"executive_review_slides"},
        }
        for artifact_id, filename in ARTIFACT_DEFINITIONS
    ]


def build_canonical_run_manifest(payload: dict[str, Any], *, depth: str | None = None, language: str | None = None) -> dict[str, Any]:
    assessment = _assessment(payload)
    scanner = _scanner(payload)
    snapshot = _snapshot(payload)
    reports = _reports(payload)
    resolved_depth = _first(depth, payload.get("assessment_depth"), payload.get("service_tier"), payload.get("assessment_type"), "core", limit=40).casefold()
    if resolved_depth in {"express", "rapid"}:
        resolved_depth = "core"
    elif resolved_depth in {"comprehensive", "full", "mid", "deep"}:
        resolved_depth = "strategic"
    resolved_language = _first(language, payload.get("report_language"), reports.get("language"), "en", limit=20)

    identity = {
        "repository": _first(payload.get("repository"), assessment.get("repository"), snapshot.get("repository"), limit=260),
        "commit_sha": _first(payload.get("commit_sha"), payload.get("snapshot_commit_sha"), assessment.get("commit_sha"), snapshot.get("commit_sha"), limit=80),
        "tree_sha": _first(payload.get("tree_sha"), snapshot.get("tree_sha"), limit=80),
        "run_id": _first(payload.get("run_id"), assessment.get("run_id"), limit=180),
        "customer_id": _first(payload.get("customer_id"), "default_customer", limit=180),
        "project_id": _first(payload.get("project_id"), "default_project", limit=180),
        "scanner_run_id": _first(scanner.get("scan_id"), scanner.get("run_id"), payload.get("scan_id"), limit=180),
        "scanner_fingerprint": _first(scanner.get("normalized_fingerprint"), scanner.get("fingerprint"), scanner.get("evidence_fingerprint"), limit=128),
        "scanner_repeatability": _first(scanner.get("repeatability_status"), scanner.get("repeatability"), "not_evaluated", limit=80),
        "evidence_bundle_hash": _evidence_bundle_hash(payload),
        "report_artifact_digest": _report_digest(payload),
        "report_language": resolved_language,
        "assessment_depth": resolved_depth,
        "created_at": _first(payload.get("generated_at"), payload.get("created_at"), payload.get("updated_at"), _now(), limit=80),
    }
    required = ("repository", "commit_sha", "run_id")
    missing = [field for field in required if not identity[field]]
    score_ledger = _section_ledger(assessment)
    modules = _module_statuses(payload, assessment, resolved_depth)
    manifest = {
        "artifact_schema": VERSION,
        "status": "blocked" if missing else "complete",
        "reason": "missing_canonical_identity:" + ",".join(missing) if missing else "",
        "identity": identity,
        "canonical_score_and_assurance_ledger": score_ledger,
        "module_status": modules,
        "technical_module_count": sum(1 for item in modules if item["module_id"] in {module_id for module_id, _ in TECHNICAL_MODULES}),
        "strategic_module_count": sum(1 for item in modules if item["module_id"] in {module_id for module_id, _ in STRATEGIC_MODULES}),
        "strategic_modules_not_assessed": [item["module_id"] for item in modules if item["status"] == "not_assessed"],
        "one_canonical_run_required": True,
        "independent_core_and_strategic_scorecards_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    manifest["canonical_manifest_sha256"] = _sha256(manifest)
    return manifest


def attach_canonical_strategic_package(payload: dict[str, Any], *, depth: str | None = None, language: str | None = None) -> dict[str, Any]:
    output = deepcopy(payload)
    assessment = _assessment(output)
    remediation = build_code_remediation_plan(output)
    risks = _risk_register(output)

    remediation_fields = (
        "finding_id", "priority", "category", "title", "confidence", "exact_location", "owner_role",
        "effort_range", "regression_risk", "recommended_change", "exit_criteria", "proposed_diff_status",
    )
    risk_fields = ("risk_id", "priority", "category", "title", "probability", "impact", "owner", "mitigation", "evidence")
    remediation_csv = _csv(remediation["items"], remediation_fields)
    risk_csv = _csv(risks, risk_fields)

    reports = _reports(output)
    reports["remediation_backlog_csv"] = remediation_csv
    reports["risk_register_csv"] = risk_csv
    reports["findings_register_json"] = _canonical_json(_records(assessment.get("findings_register")))
    reports["score_assurance_ledger_json"] = _canonical_json(_section_ledger(assessment))
    reports["code_remediation_plan_json"] = _canonical_json(remediation)

    output["report_package"] = reports if output.get("report_package") is not None else output.get("report_package")
    if isinstance(output.get("reports"), dict) or not output.get("report_package"):
        output["reports"] = reports
    output["code_remediation_plan"] = remediation
    output["risk_register"] = risks

    manifest = build_canonical_run_manifest(output, depth=depth, language=language)
    evidence_manifest = {
        "artifact_schema": VERSION,
        "canonical_run_manifest_sha256": manifest["canonical_manifest_sha256"],
        "repository": manifest["identity"]["repository"],
        "commit_sha": manifest["identity"]["commit_sha"],
        "tree_sha": manifest["identity"]["tree_sha"],
        "run_id": manifest["identity"]["run_id"],
        "scanner_run_id": manifest["identity"]["scanner_run_id"],
        "scanner_fingerprint": manifest["identity"]["scanner_fingerprint"],
        "evidence_bundle_hash": manifest["identity"]["evidence_bundle_hash"],
        "report_artifact_digest": manifest["identity"]["report_artifact_digest"],
        "exports": {
            "remediation_backlog_csv_sha256": _sha256(remediation_csv.encode("utf-8")),
            "risk_register_csv_sha256": _sha256(risk_csv.encode("utf-8")),
            "code_remediation_plan_json_sha256": _sha256(remediation),
            "score_assurance_ledger_json_sha256": _sha256(manifest["canonical_score_and_assurance_ledger"]),
        },
        "raw_secret_material_included": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    reports["evidence_manifest_json"] = _canonical_json(evidence_manifest)
    output["canonical_run_manifest"] = manifest
    output["evidence_manifest"] = evidence_manifest
    output["premium_artifact_manifest"] = _artifact_statuses(output, manifest["identity"]["assessment_depth"])
    output["canonical_package_contract"] = {
        "artifact_schema": VERSION,
        "status": manifest["status"],
        "canonical_run_manifest_present": True,
        "score_assurance_ledger_present": bool(manifest["canonical_score_and_assurance_ledger"]),
        "code_remediation_plan_present": True,
        "risk_register_present": True,
        "evidence_manifest_present": True,
        "proposed_code_changes_are_review_only": True,
        "automatic_approval": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output


def validate_final_accepted_package(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = _record(payload.get("canonical_run_manifest")) or build_canonical_run_manifest(payload)
    scanner = _scanner(payload)
    module_status = _records(manifest.get("module_status"))
    reports = _reports(payload)
    approval = _record(payload.get("approval") or reports.get("approval_record"))
    blockers: list[str] = []
    if manifest.get("status") != "complete":
        blockers.append(str(manifest.get("reason") or "canonical_run_manifest_incomplete"))
    if scanner and str(scanner.get("status") or "").casefold() != "complete":
        blockers.append("scanner_suite_not_complete")
    if scanner and scanner.get("snapshot_match") is not True:
        blockers.append("scanner_snapshot_identity_not_verified")
    if not _section_ledger(_assessment(payload)):
        blockers.append("canonical_score_and_assurance_ledger_missing")
    if not (_records(_assessment(payload).get("findings_register")) or _record(payload.get("code_remediation_plan")).get("status") == "not_applicable"):
        blockers.append("findings_and_remediation_register_missing")
    missing_strategic = [item["module_id"] for item in module_status if item.get("status") == "not_assessed"]
    if manifest.get("identity", {}).get("assessment_depth") == "strategic" and missing_strategic:
        blockers.append("strategic_modules_not_assessed:" + ",".join(missing_strategic))
    if approval.get("decision") not in {"approved", "accepted"}:
        blockers.append("named_human_approval_missing")
    if not _first(approval.get("reviewer"), approval.get("reviewed_by"), limit=180):
        blockers.append("named_reviewer_missing")
    return {
        "artifact_schema": VERSION,
        "status": "accepted" if not blockers else "blocked",
        "blockers": blockers,
        "final_accepted_allowed": not blockers,
        "human_review_required": True,
        "client_delivery_allowed": not blockers,
    }


__all__ = [
    "ARTIFACT_DEFINITIONS",
    "STRATEGIC_MODULES",
    "TECHNICAL_MODULES",
    "VERSION",
    "attach_canonical_strategic_package",
    "build_canonical_run_manifest",
    "build_code_remediation_plan",
    "validate_final_accepted_package",
]
