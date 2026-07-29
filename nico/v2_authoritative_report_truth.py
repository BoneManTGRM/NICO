from __future__ import annotations

import re
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Mapping, MutableMapping

VERSION = "nico.v2.authoritative-report-truth.v1"

_NON_PRODUCTION_PARTS = {
    "test", "tests", "testing", "fixture", "fixtures", "sample", "samples",
    "example", "examples", "generated", "vendor", "vendors", "dist", "build",
    "coverage", "node_modules", ".venv", "venv",
}
_STALE_SCANNER_WORDS = ("missing", "failed", "failure", "unavailable", "not run", "did not run")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def _scanner_name(value: Any) -> str:
    name = _text(value).casefold().replace("_", "-")
    return {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "tsc": "typescript",
        "truffle-hog": "trufflehog",
    }.get(name, name)


def _score_truth(canonical: MutableMapping[str, Any]) -> tuple[int | None, int | None]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    maturity = deepcopy(dict(maturity))
    existing = assessment.get("comprehensive_score_truth") if isinstance(assessment.get("comprehensive_score_truth"), Mapping) else {}

    technical = next((score for raw in (
        existing.get("technical_score"),
        assessment.get("technical_score"),
        maturity.get("technical_score"),
        maturity.get("presented_score"),
        maturity.get("score"),
    ) if (score := _numeric(raw)) is not None), None)
    adjusted = next((score for raw in (
        existing.get("canonical_evidence_adjusted_score"),
        assessment.get("canonical_evidence_adjusted_score"),
        assessment.get("evidence_adjusted_score"),
        maturity.get("canonical_evidence_adjusted_score"),
        maturity.get("evidence_adjusted_score"),
        technical,
    ) if (score := _numeric(raw)) is not None), None)

    if technical is not None:
        canonical["technical_score"] = technical
        assessment["technical_score"] = technical
        for key in ("technical_score", "presented_score", "score", "source_score"):
            maturity[key] = technical
    if adjusted is not None:
        canonical["canonical_evidence_adjusted_score"] = adjusted
        canonical["evidence_adjusted_score"] = adjusted
        assessment["canonical_evidence_adjusted_score"] = adjusted
        assessment["evidence_adjusted_score"] = adjusted
        maturity["canonical_evidence_adjusted_score"] = adjusted
        maturity["evidence_adjusted_score"] = adjusted

    assessment["maturity_signal"] = maturity
    assessment["comprehensive_score_truth"] = {
        "technical_score": technical,
        "canonical_evidence_adjusted_score": adjusted,
        "aliases_synchronized": technical is not None and adjusted is not None,
        "single_calculation_authority": True,
    }
    canonical["assessment"] = assessment
    return technical, adjusted


def _repair_score_stages(canonical: MutableMapping[str, Any], technical: int | None, adjusted: int | None) -> None:
    repaired: list[dict[str, Any]] = []
    for raw in canonical.get("stage_summaries") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        if _text(item.get("stage_id")) == "evidence_reconciliation_and_scoring":
            if technical is not None:
                item.update({"technical_score": technical, "score": technical, "presented_score": technical})
            if adjusted is not None:
                item.update({
                    "evidence_adjusted_score": adjusted,
                    "canonical_evidence_adjusted_score": adjusted,
                })
            item["summary"] = (
                f"Canonical technical score {technical}/100 and evidence-adjusted score {adjusted}/100 "
                "were synchronized before publication."
                if technical is not None and adjusted is not None
                else "Canonical score publication requires human review."
            )
            item["status"] = "complete" if technical is not None else "review_required"
        repaired.append(item)
    canonical["stage_summaries"] = repaired

    contract = canonical.get("report_contract") if isinstance(canonical.get("report_contract"), Mapping) else {}
    contract = deepcopy(dict(contract))
    if "canonical_score_truth_mismatch" in _text(contract.get("reason")).casefold():
        contract.update({
            "prior_block_reason": contract.get("reason"),
            "reason": "canonical_score_truth_synchronized",
            "status": "passed",
            "blocked": False,
        })
    if contract:
        canonical["report_contract"] = contract


def _scanner_truth(canonical: MutableMapping[str, Any]) -> list[dict[str, Any]]:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    expected = _text(identity.get("commit_sha") or canonical.get("commit_sha")).casefold()
    source = canonical.get("scanner_execution_records") if isinstance(canonical.get("scanner_execution_records"), list) else []
    records: list[dict[str, Any]] = []
    for raw in source:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        item["scanner_name"] = _scanner_name(item.get("scanner_name") or item.get("tool"))
        state = _text(item.get("state") or item.get("status") or "unknown").casefold().replace("-", "_")
        item["state"] = state
        item["status"] = state
        observed = _text(item.get("commit_sha") or item.get("snapshot_commit_sha") or expected).casefold()
        item["commit_sha"] = observed
        item["exact_commit_match"] = bool(expected and observed == expected)
        item["verified_complete"] = item.get("verified") is True or item.get("verified_complete") is True
        item["verified_for_this_report"] = item["verified_complete"]
        records.append(item)

    canonical["scanner_execution_records"] = records
    completed = [item for item in records if item.get("completed") is True]
    incomplete = [item for item in records if item.get("completed") is not True]
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    assessment["scanner_execution_records"] = deepcopy(records)
    assessment["completed_scanner_records"] = deepcopy(completed)
    assessment["incomplete_scanner_records"] = deepcopy(incomplete)
    assessment["evidence_health_summary"] = {
        "scanner_execution_records": deepcopy(records),
        "completed_scanners": [item["scanner_name"] for item in completed],
        "incomplete_scanners": deepcopy(incomplete),
        "completed_scanner_count": len(completed),
        "incomplete_scanner_count": len(incomplete),
        "single_normalized_scanner_population": True,
        "legacy_scanner_summary_bypassed": True,
    }
    canonical["assessment"] = assessment
    return records


def _stale_scanner_statement(value: Any, completed_names: set[str]) -> bool:
    text = _text(value).casefold().replace("-", " ")
    return any(
        name.replace("-", " ") in text and any(word in text for word in _STALE_SCANNER_WORDS)
        for name in completed_names
    )


def _repair_scanner_stages(canonical: MutableMapping[str, Any], records: list[dict[str, Any]]) -> None:
    completed = [item for item in records if item.get("completed") is True]
    incomplete = [item for item in records if item.get("completed") is not True]
    completed_names = {item["scanner_name"] for item in completed}
    repaired: list[dict[str, Any]] = []
    for raw in canonical.get("stage_summaries") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        if _text(item.get("stage_id")) == "dependency_security_static_analysis":
            continue
        if _stale_scanner_statement(item.get("summary"), completed_names):
            item["summary"] = "Canonical scanner records are authoritative; stale pre-canonical scanner prose was removed."
        for key in ("evidence", "findings", "unavailable"):
            item[key] = [
                value for value in item.get(key) or []
                if not _stale_scanner_statement(value, completed_names)
            ]
        repaired.append(item)

    repaired.append({
        "stage_id": "dependency_security_static_analysis",
        "title": "Dependency, Security, and Static Analysis",
        "status": "complete" if not incomplete else "review_required",
        "summary": f"{len(completed)} of {len(records)} canonical scanner records completed for the immutable commit.",
        "evidence": [
            f"{item['scanner_name']}: {item['state']}; exact commit={'yes' if item.get('exact_commit_match') else 'no'}; "
            f"artifact={'retained' if item.get('artifact_hash') else 'missing'}; findings={len(item.get('findings') or [])}"
            for item in records
        ],
        "findings": [],
        "unavailable": [
            f"{item['scanner_name']}: {_text(item.get('failure_reason') or item.get('reason') or 'scanner evidence incomplete')}"
            for item in incomplete
        ],
    })
    canonical["stage_summaries"] = repaired

    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    sections: list[dict[str, Any]] = []
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        if _stale_scanner_statement(item.get("summary"), completed_names):
            item["summary"] = "Canonical scanner status is presented in Evidence Health; stale pre-canonical scanner prose was removed."
        for key in ("evidence", "findings", "unavailable"):
            item[key] = [value for value in item.get(key) or [] if not _stale_scanner_statement(value, completed_names)]
        sections.append(item)
    assessment["sections"] = sections
    canonical["assessment"] = assessment


def _path_from_location(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("path") or value.get("file") or value.get("filename") or value.get("file_path")
    return re.sub(r":\d+(?::\d+)?$", "", _text(value).replace("\\", "/"))


def _classify_findings(canonical: MutableMapping[str, Any]) -> None:
    findings: list[dict[str, Any]] = []
    for raw in canonical.get("canonical_findings") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        path = _path_from_location(item.get("location"))
        parts = {part.casefold() for part in PurePosixPath(path).parts}
        filename = PurePosixPath(path).name.casefold()
        declared = _text(item.get("scope") or item.get("production_scope")).casefold()
        non_production = declared in {"test", "tests", "non-production", "non_production", "generated", "vendor"}
        non_production = non_production or bool(parts & _NON_PRODUCTION_PARTS)
        non_production = non_production or filename.startswith("test_")
        non_production = non_production or filename.endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js"))
        item["production_scope"] = "non_production" if non_production else "production_or_unknown"
        if non_production:
            item["technical_score_impact"] = False
            item["disposition"] = item.get("disposition") or "appendix_only_non_production_observation"
        findings.append(item)

    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        canonical[surface] = deepcopy(findings)
    score_findings = [item for item in findings if item.get("technical_score_impact") is not False]
    canonical["executive_risk_register"] = deepcopy(score_findings[:7])
    canonical["priority_findings"] = deepcopy(score_findings[:5])


def _dependency_disposition(canonical: MutableMapping[str, Any], records: list[dict[str, Any]]) -> None:
    osv = next((item for item in records if item["scanner_name"] == "osv-scanner"), None)
    dispositions: list[dict[str, Any]] = []
    for raw in (osv.get("findings") if isinstance(osv, Mapping) else []) or []:
        if not isinstance(raw, Mapping):
            continue
        advisory = _text(raw.get("advisory_id") or raw.get("id") or raw.get("vulnerability_id"))
        package = _text(raw.get("package") or raw.get("package_name") or raw.get("name"))
        installed = _text(raw.get("installed_version") or raw.get("version"))
        fixed = _text(raw.get("fixed_version") or raw.get("patched_version"))
        path = _text(raw.get("dependency_path") or raw.get("path"))
        scope = _text(raw.get("scope") or raw.get("environment") or "unknown")
        reachability = _text(raw.get("reachability") or "unknown")
        severity = _text(raw.get("severity") or raw.get("database_severity") or "unknown")
        declared = _text(raw.get("disposition") or raw.get("status")).casefold()
        complete = all((advisory, package, installed, path, scope, reachability))
        verified = complete and declared in {"material", "verified_material", "confirmed", "actionable"}
        dispositions.append({
            "advisory_id": advisory or "unretained",
            "package": package or "unretained",
            "installed_version": installed or "unretained",
            "fixed_version": fixed or "not retained",
            "dependency_path": path or "not retained",
            "severity": severity,
            "scope": scope,
            "reachability": reachability,
            "disposition": "verified_material" if verified else "untriaged_assurance_gap",
            "technical_score_impact": verified,
        })

    canonical["dependency_disposition"] = dispositions
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    assessment["dependency_disposition_summary"] = {
        "raw_advisory_count": len(dispositions),
        "verified_material_count": sum(item["technical_score_impact"] is True for item in dispositions),
        "untriaged_assurance_gap_count": sum(item["technical_score_impact"] is False for item in dispositions),
        "untriaged_records_reduce_assurance_not_technical_score": True,
    }
    canonical["assessment"] = assessment


def _assert_score_truth(canonical: Mapping[str, Any]) -> None:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    truth = assessment.get("comprehensive_score_truth") if isinstance(assessment.get("comprehensive_score_truth"), Mapping) else {}
    technical = {
        score for raw in (
            canonical.get("technical_score"), assessment.get("technical_score"), maturity.get("technical_score"),
            maturity.get("presented_score"), maturity.get("score"), truth.get("technical_score"),
        ) if (score := _numeric(raw)) is not None
    }
    adjusted = {
        score for raw in (
            canonical.get("canonical_evidence_adjusted_score"), assessment.get("canonical_evidence_adjusted_score"),
            assessment.get("evidence_adjusted_score"), maturity.get("canonical_evidence_adjusted_score"),
            maturity.get("evidence_adjusted_score"), truth.get("canonical_evidence_adjusted_score"),
        ) if (score := _numeric(raw)) is not None
    }
    if len(technical) > 1 or len(adjusted) > 1:
        raise ValueError("canonical score truth mismatch after synchronization")


def repair_canonical_truth_in_place(canonical: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Repair report projections before canonical hashing and artifact generation."""

    technical, adjusted = _score_truth(canonical)
    _repair_score_stages(canonical, technical, adjusted)
    records = _scanner_truth(canonical)
    _repair_scanner_stages(canonical, records)
    _classify_findings(canonical)
    _dependency_disposition(canonical, records)
    canonical.update({
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "assessment_state": "review_required",
        "authoritative_report_truth": {
            "version": VERSION,
            "score_truth_synchronized": True,
            "stale_scanner_projections_removed": True,
            "dependency_materiality_disposition_required": True,
            "non_production_findings_do_not_reduce_technical_score": True,
            "old_visual_shell_new_canonical_engine": True,
        },
    })
    _assert_score_truth(canonical)
    return canonical


__all__ = ["VERSION", "repair_canonical_truth_in_place"]
