from __future__ import annotations

import io
import re
import shutil
import sys
import tokenize
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from nico.ci_history_classification_v1 import classify_workflow_history
from nico.scanner_evidence_pipeline_v1 import REQUIRED_EVIDENCE_TOOLS

VERSION = "nico.phase5_report_truth.v1"
_PATCH_MARKER = "_nico_phase5_report_truth_v1"

BASELINE = {
    "commit_sha": "b376f6807953de5a41e41b3e408e79da715bfa0c",
    "technical_maturity": 85,
    "evidence_adjusted_readiness": 83,
    "scanner_statuses": {
        "bandit": "failed",
        "eslint": "failed",
        "gitleaks": "partial",
        "osv-scanner": "partial",
    },
    "complexity": {
        "_build_markdown": 108,
        "_build_pdf": 116,
        "_build_complexity": 94,
        "build_comprehensive_report_package": 94,
        "AssessmentWorkspace": 114,
        "FinalReviewWorkspace": 61,
        "FullRunPage": 93,
        "Page": 72,
    },
}

_SCANNER_CATEGORIES = {
    "pip-audit": "dependency",
    "npm-audit": "dependency",
    "osv-scanner": "dependency",
    "bandit": "static",
    "semgrep": "static",
    "eslint": "static",
    "typescript": "static",
    "gitleaks": "secret",
    "trufflehog": "secret",
}
_SECTION_IDS = {
    "dependency": "dependency_health",
    "static": "static_analysis",
    "secret": "secrets_review",
}
_CODE_SUFFIXES = (".py", ".js", ".jsx", ".ts", ".tsx")


def _text(value: Any, limit: int = 800) -> str:
    return " ".join(str(value or "").split())[:limit]


def _sha(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if len(text) == 40 and all(character in "0123456789abcdef" for character in text) else ""


def _dedupe(values: Iterable[str], limit: int = 100) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _python_without_strings_and_comments(source: str) -> str:
    lines = source.splitlines(keepends=True)
    mutable = [list(line) for line in lines]
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type not in {tokenize.STRING, tokenize.COMMENT}:
                continue
            (start_line, start_col), (end_line, end_col) = token.start, token.end
            for line_number in range(start_line, end_line + 1):
                if line_number < 1 or line_number > len(mutable):
                    continue
                line = mutable[line_number - 1]
                left = start_col if line_number == start_line else 0
                right = end_col if line_number == end_line else len(line)
                for index in range(max(0, left), min(len(line), right)):
                    if line[index] not in "\r\n":
                        line[index] = " "
    except (tokenize.TokenError, IndentationError):
        return source
    return "".join("".join(line) for line in mutable)


def scan_files_executable_only(files: dict[str, str]) -> dict[str, Any]:
    """Retain broad secret/TODO inspection while applying code-risk rules only to executable source.

    Python strings and comments are removed before risk-pattern matching. This prevents scanner
    rule examples and documentation literals from being reported as executable insecure behavior,
    while real calls such as requests.get(..., verify=False) remain detectable.
    """

    from nico import hosted_assessment as hosted

    todos: list[str] = []
    risks: list[str] = []
    secrets: list[str] = []
    test_paths = [path for path in files if "test" in path.lower() or path.startswith("tests/")]
    docs = [path for path in files if path.lower().endswith(".md") or path.startswith("docs/")]
    for path, text in files.items():
        raw_lines = text.splitlines()
        for line_no, line in enumerate(raw_lines, 1):
            stripped = line.strip()
            upper = stripped.upper()
            if "TODO" in upper or "FIXME" in upper or "SECURITY" in upper:
                todos.append(f"{path}:{line_no}: {stripped[:140]}")
            for name, pattern in hosted.SECRET_PATTERNS:
                match = pattern.search(line)
                if match:
                    evidence = match.group(0)
                    secrets.append(
                        f"{path}:{line_no}: potential {name} evidence {hosted.mask_secret(evidence)}"
                    )

        if not path.casefold().endswith(_CODE_SUFFIXES):
            continue
        risk_source = _python_without_strings_and_comments(text) if path.casefold().endswith(".py") else text
        for line_no, line in enumerate(risk_source.splitlines(), 1):
            for name, pattern, message in hosted.RISK_PATTERNS:
                if pattern.search(line):
                    risks.append(f"{path}:{line_no}: {name} — {message}")

    return {
        "todos": todos,
        "risks": risks,
        "secrets": secrets,
        "test_paths": test_paths,
        "docs": docs,
        "risk_scan_method": "executable_source_token_aware_v1",
        "configuration_literals_treated_as_executable": False,
    }


def _context_from_mapping(value: dict[str, Any], inherited: dict[str, str]) -> dict[str, str]:
    context = dict(inherited)
    checkout = value.get("checkout") if isinstance(value.get("checkout"), dict) else {}
    provenance = value.get("provenance") if isinstance(value.get("provenance"), dict) else {}
    for candidate in (
        value.get("target_commit_sha"),
        value.get("snapshot_commit_sha"),
        checkout.get("commit_sha"),
        provenance.get("target_commit_sha"),
    ):
        commit = _sha(candidate)
        if commit:
            context["commit_sha"] = commit
            break
    run_id = _text(value.get("run_id"), 180)
    if run_id:
        context["run_id"] = run_id
    return context


def _normalized_scanner_record(
    tool: str,
    payload: dict[str, Any],
    *,
    context: dict[str, str],
    path: str,
    target_commit: str,
) -> dict[str, Any]:
    commit_sha = _sha(payload.get("target_commit_sha")) or context.get("commit_sha", "")
    status = _text(payload.get("status") or "unknown", 40).casefold()
    exact_commit = bool(target_commit and commit_sha == target_commit)
    history_ready = payload.get("scans_git_history") is not True or payload.get("full_history_verified") is True
    execution_complete = (
        status == "completed"
        and payload.get("verified_for_this_report") is True
        and payload.get("output_capture_complete") is True
        and payload.get("raw_artifact_capture_complete") is True
        and payload.get("returncode_valid") is not False
        and payload.get("timed_out") is not True
        and history_ready
        and exact_commit
    )
    return {
        "tool": tool,
        "category": _SCANNER_CATEGORIES.get(tool, _text(payload.get("category"), 40) or "unknown"),
        "status": status,
        "execution_complete": execution_complete,
        "exact_commit_match": exact_commit,
        "target_commit_sha": commit_sha,
        "run_id": _text(payload.get("run_id") or context.get("run_id"), 180),
        "scanner_tool_version": _text(payload.get("scanner_tool_version"), 180),
        "findings_count": int(payload.get("findings_count") or len(payload.get("findings") or [])),
        "artifact_hash": _text(payload.get("artifact_hash"), 128),
        "raw_artifact_sha256": _text(payload.get("raw_artifact_sha256"), 128),
        "deterministic_fingerprint": _text(payload.get("deterministic_fingerprint"), 128),
        "failure_reason": _text(
            payload.get("failure_or_unavailable_reason") or payload.get("reason"),
            1000,
        ),
        "source_path": path,
        "findings": [item for item in payload.get("findings") or [] if isinstance(item, dict)][:500],
    }


def _collect_scanner_records(
    value: Any,
    *,
    target_commit: str,
    path: str = "stage_results",
    context: dict[str, str] | None = None,
    inferred_tool: str = "",
    output: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    records = output if output is not None else []
    inherited = dict(context or {})
    if isinstance(value, dict):
        local = _context_from_mapping(value, inherited)
        tool = _text(value.get("tool") or value.get("scanner") or inferred_tool, 80).casefold()
        if tool in REQUIRED_EVIDENCE_TOOLS and "status" in value:
            records.append(
                _normalized_scanner_record(
                    tool,
                    value,
                    context=local,
                    path=path,
                    target_commit=target_commit,
                )
            )
        for key, child in value.items():
            child_tool = str(key).casefold() if str(key).casefold() in REQUIRED_EVIDENCE_TOOLS else ""
            _collect_scanner_records(
                child,
                target_commit=target_commit,
                path=f"{path}.{key}",
                context=local,
                inferred_tool=child_tool,
                output=records,
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_scanner_records(
                child,
                target_commit=target_commit,
                path=f"{path}[{index}]",
                context=inherited,
                inferred_tool=inferred_tool,
                output=records,
            )
    return records


def _authoritative_scanners(stage_results: dict[str, Any], target_commit: str) -> dict[str, dict[str, Any]]:
    candidates = _collect_scanner_records(stage_results, target_commit=target_commit)
    output: dict[str, dict[str, Any]] = {}
    for tool in REQUIRED_EVIDENCE_TOOLS:
        items = [item for item in candidates if item["tool"] == tool]
        if not items:
            continue
        items.sort(
            key=lambda item: (
                bool(item["exact_commit_match"]),
                bool(item["execution_complete"]),
                bool(item["artifact_hash"]),
                bool(item["deterministic_fingerprint"]),
                item["source_path"],
            ),
            reverse=True,
        )
        output[tool] = items[0]
    return output


def _find_schema(value: Any, schema: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("schema") == schema:
            return value
        for child in value.values():
            found = _find_schema(child, schema)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_schema(child, schema)
            if found is not None:
                return found
    return None


def _section(assessment: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in assessment.get("sections") or []:
        if isinstance(item, dict) and item.get("id") == section_id:
            return item
    return None


def _scanner_line(record: dict[str, Any]) -> str:
    return (
        f"{record['tool']}: status={record['status']}; exact_commit_match={record['exact_commit_match']}; "
        f"verified_complete={record['execution_complete']}; findings={record['findings_count']}; "
        f"artifact_hash={record['artifact_hash'] or 'unavailable'}"
    )


def _reconcile_scanner_health(
    assessment: dict[str, Any],
    stage_results: dict[str, Any],
    target_commit: str,
) -> dict[str, dict[str, Any]]:
    records = _authoritative_scanners(stage_results, target_commit)
    if not records:
        return records

    completed = sorted(tool for tool, record in records.items() if record["execution_complete"])
    incomplete: list[dict[str, Any]] = []
    for tool in REQUIRED_EVIDENCE_TOOLS:
        record = records.get(tool)
        if record and record["execution_complete"]:
            continue
        reason = record["failure_reason"] if record else "No exact-SHA current-run scanner record was retained."
        status = record["status"] if record else "missing"
        incomplete.append(
            {
                "scanner": tool,
                "status": status,
                "required": True,
                "affected_categories": _SCANNER_CATEGORIES.get(tool, "unknown"),
                "confidence_impact": "Material reduction",
                "remediation": reason or "Repair the scanner boundary and rerun against the same immutable commit.",
                "exact_commit_match": bool(record and record["exact_commit_match"]),
                "artifact_hash": record["artifact_hash"] if record else "",
            }
        )

    assessment["evidence_health_summary"] = {
        "schema": "nico.phase5.scanner_report_truth.v1",
        "confidence_effect": (
            "Every required scanner has complete retained exact-SHA evidence."
            if not incomplete
            else "Required scanner limitations are retained; incomplete evidence remains review-limited and cannot be represented as clean."
        ),
        "completed_scanners": completed,
        "incomplete_scanners": incomplete,
        "target_commit_sha": target_commit,
        "report_status_derived_from_retained_artifact": True,
        "scanner_records": {tool: {key: value for key, value in record.items() if key != "findings"} for tool, record in sorted(records.items())},
    }

    by_category: dict[str, list[dict[str, Any]]] = {"dependency": [], "static": [], "secret": []}
    for record in records.values():
        by_category.setdefault(record["category"], []).append(record)
    for category, category_records in by_category.items():
        section = _section(assessment, _SECTION_IDS[category])
        if section is None:
            continue
        evidence = [
            line
            for line in section.get("evidence") or []
            if not any(tool in _text(line).casefold() for tool in REQUIRED_EVIDENCE_TOOLS)
        ]
        evidence.extend(_scanner_line(record) for record in sorted(category_records, key=lambda item: item["tool"]))
        section["evidence"] = _dedupe(evidence, 80)
        unavailable = [
            line
            for line in section.get("unavailable") or []
            if not any(tool in _text(line).casefold() for tool in REQUIRED_EVIDENCE_TOOLS)
        ]
        unavailable.extend(
            f"{record['tool']} exact-SHA evidence remains {record['status']}: {record['failure_reason'] or 'completion requirements were not met'}"
            for record in category_records
            if not record["execution_complete"]
        )
        section["unavailable"] = _dedupe(unavailable, 80)
        section["assurance_source"] = "retained_exact_sha_scanner_artifacts"

    findings = [item for item in assessment.get("findings_register") or [] if isinstance(item, dict)]
    retained_findings: list[dict[str, Any]] = []
    for item in findings:
        title = _text(item.get("title")).casefold()
        category = _text(item.get("category")).casefold()
        removable = False
        for tool, record in records.items():
            if not record["execution_complete"] or tool not in title:
                continue
            if category in {"evidence", "dependency", "secret", "static"} and any(
                token in title for token in ("unavailable", "incomplete", "did not produce", "failed", "partial")
            ):
                removable = True
                break
        if not removable:
            retained_findings.append(item)
    assessment["findings_register"] = retained_findings
    return records


def _reconcile_ci_history(assessment: dict[str, Any], stage_results: dict[str, Any]) -> dict[str, Any] | None:
    summary = _find_schema(stage_results, "nico.ci_history_summary.v1")
    if not isinstance(summary, dict):
        return None
    assessment["ci_history_classification"] = deepcopy(summary)
    historical = summary.get("historical_reliability") if isinstance(summary.get("historical_reliability"), dict) else {}
    counts = historical.get("classified_counts") if isinstance(historical.get("classified_counts"), dict) else {}
    section = _section(assessment, "ci_cd")
    if section is not None:
        classification_line = "Workflow outcome classes: " + "; ".join(
            f"{key}={value}" for key, value in sorted(counts.items())
        )
        evidence = [
            line for line in section.get("evidence") or []
            if not _text(line).casefold().startswith("workflow outcome classes:")
        ]
        evidence.extend(
            [
                classification_line,
                f"Historical genuine-failure rate: {historical.get('genuine_failure_rate')}",
                f"Current required-check health green: {(summary.get('current_branch_health') or {}).get('green')}",
                "Cancellations are excluded from the genuine-failure rate.",
            ]
        )
        section["evidence"] = _dedupe(evidence, 80)
        findings = [
            line
            for line in section.get("findings") or []
            if "non-success" not in _text(line).casefold() and "cause classification" not in _text(line).casefold()
        ]
        genuine = int(counts.get("genuine_failure") or 0)
        unknown = int(counts.get("unknown_review_required") or 0)
        infra = int(counts.get("infrastructure_fault") or 0)
        if genuine or unknown or infra:
            findings.append(
                f"Classified CI history retains genuine_failures={genuine}, infrastructure_faults={infra}, and unknown_review_required={unknown}."
            )
        section["findings"] = _dedupe(findings, 60)
        section["historical_reliability_classified"] = True
    return summary


def _complexity_snapshot(assessment: dict[str, Any]) -> dict[str, int]:
    output: dict[str, int] = {}
    for item in assessment.get("findings_register") or []:
        if not isinstance(item, dict) or _text(item.get("category")).casefold() != "architecture":
            continue
        title = _text(item.get("title"))
        evidence = _text(item.get("evidence") or item.get("fact"), 2000)
        match = re.search(r"cyclomatic[_ ]complexity\s*=\s*(\d+)", evidence, re.IGNORECASE)
        if not match:
            continue
        name = title.split(":", 1)[-1].strip() if ":" in title else title
        if name:
            output[name] = int(match.group(1))
    return output


def _phase5_outcomes(
    assessment: dict[str, Any],
    scanners: dict[str, dict[str, Any]],
    ci_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    current_scanners = {
        tool: record["status"] if not record["execution_complete"] else "completed"
        for tool, record in sorted(scanners.items())
    }
    scanner_changes = {
        tool: {"before": before, "after": current_scanners.get(tool, "missing")}
        for tool, before in BASELINE["scanner_statuses"].items()
        if current_scanners.get(tool, "missing") != before
    }
    current_complexity = _complexity_snapshot(assessment)
    complexity_changes = {
        name: {"before": before, "after": current_complexity[name], "delta": current_complexity[name] - before}
        for name, before in BASELINE["complexity"].items()
        if name in current_complexity and current_complexity[name] != before
    }
    tls_open = any(
        "tls_verify_disabled" in _text(item.get("title")).casefold()
        for item in assessment.get("findings_register") or []
        if isinstance(item, dict)
    )
    return {
        "schema": VERSION,
        "baseline_commit_sha": BASELINE["commit_sha"],
        "current_commit_sha": (assessment.get("evidence_health_summary") or {}).get("target_commit_sha"),
        "scanner_status_changes": scanner_changes,
        "current_scanner_statuses": current_scanners,
        "ci_history_classification_visible": ci_summary is not None,
        "tls_verify_disabled_finding_open": tls_open,
        "complexity_changes": complexity_changes,
        "unchanged_complexity_hotspots": sorted(
            name for name, before in BASELINE["complexity"].items()
            if current_complexity.get(name) == before
        ),
        "truth_rule": "Only exact-SHA retained evidence changes report outcomes; unchanged risks remain visible.",
    }


def reconcile_phase5_report_truth(
    assessment: dict[str, Any],
    stage_results: dict[str, Any],
) -> dict[str, Any]:
    output = deepcopy(assessment)
    target_commit = ""
    for value in stage_results.values():
        if isinstance(value, dict):
            target_commit = _sha(value.get("commit_sha") or value.get("snapshot_commit_sha") or value.get("target_commit_sha"))
            if target_commit:
                break
    scanners = _reconcile_scanner_health(output, stage_results, target_commit)
    ci_summary = _reconcile_ci_history(output, stage_results)
    outcomes = _phase5_outcomes(output, scanners, ci_summary)
    output["phase5_verified_outcomes"] = outcomes

    sections = [item for item in output.get("sections") or [] if isinstance(item, dict)]
    sections = [item for item in sections if item.get("id") != "phase5_verified_outcomes"]
    scanner_change_count = len(outcomes["scanner_status_changes"])
    complexity_change_count = len(outcomes["complexity_changes"])
    ci_text = "CI history classification is report-visible." if outcomes["ci_history_classification_visible"] else "CI classification evidence was not retained in this run."
    tls_text = "TLS verification finding remains open." if outcomes["tls_verify_disabled_finding_open"] else "No executable disabled-TLS finding is open in the current exact-SHA finding ledger."
    sections.append(
        {
            "id": "phase5_verified_outcomes",
            "label": "Verified Change Since Phase 5 Baseline",
            "score": None,
            "presented_score": None,
            "score_value": None,
            "exclude_from_maturity": True,
            "status": "green" if scanner_change_count or complexity_change_count or outcomes["ci_history_classification_visible"] else "gray",
            "summary": (
                f"Exact-SHA comparison recorded {scanner_change_count} scanner-status change(s) and "
                f"{complexity_change_count} analyzer-measured complexity change(s). {ci_text} {tls_text}"
            ),
            "evidence": [
                f"Baseline commit: {BASELINE['commit_sha']}",
                f"Scanner status changes: {outcomes['scanner_status_changes']}",
                f"Complexity changes: {outcomes['complexity_changes']}",
                ci_text,
                tls_text,
            ],
            "findings": [],
            "unavailable": [
                "Unchanged baseline risks remain open and are not hidden by this comparison."
            ] if outcomes["unchanged_complexity_hotspots"] else [],
            "human_review_required": True,
        }
    )
    output["sections"] = sections
    output["human_review_required"] = True
    output["client_ready"] = False
    output["client_delivery_allowed"] = False
    return output


def _patch_snapshot_collection() -> None:
    from nico import hosted_assessment
    from nico import snapshot_repository_evidence as snapshot

    original_scan = hosted_assessment.scan_files
    if getattr(original_scan, _PATCH_MARKER, False):
        return
    setattr(scan_files_executable_only, _PATCH_MARKER, True)
    hosted_assessment.scan_files = scan_files_executable_only
    for module in tuple(sys.modules.values()):
        name = str(getattr(module, "__name__", ""))
        if name.startswith("nico.") and getattr(module, "scan_files", None) is original_scan:
            setattr(module, "scan_files", scan_files_executable_only)

    original_summary = snapshot._workflow_summary

    def classified_workflow_summary(
        workflows: dict[str, str],
        runs: list[dict[str, Any]],
        ci: dict[str, Any],
        snapshot_sha: str,
    ) -> dict[str, Any]:
        summary = original_summary(workflows, runs, ci, snapshot_sha)
        current_checks = ci.get("current_required_checks") if isinstance(ci.get("current_required_checks"), dict) else {}
        classified = classify_workflow_history(runs, current_required_checks=current_checks)
        summary["classified_history"] = classified
        counts = classified["historical_reliability"]["classified_counts"]
        summary["genuine_failure_runs"] = int(counts.get("genuine_failure") or 0)
        summary["cancelled_or_superseded_runs"] = sum(
            int(counts.get(key) or 0)
            for key in ("superseded_cancellation", "manual_cancellation", "expected_or_unclassified_cancellation")
        )
        summary["infrastructure_fault_runs"] = int(counts.get("infrastructure_fault") or 0)
        summary["unknown_review_required_runs"] = int(counts.get("unknown_review_required") or 0)
        summary["historical_failure_rate"] = classified["historical_reliability"]["genuine_failure_rate"]
        summary["non_success_runs_are_cause_classified"] = True
        return summary

    setattr(classified_workflow_summary, _PATCH_MARKER, True)
    snapshot._workflow_summary = classified_workflow_summary

    original_collect = snapshot.collect_snapshot_repository_evidence

    def collect_with_phase5_truth(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        bundle, complexity = original_collect(*args, **kwargs)
        if isinstance(bundle, dict):
            code = bundle.get("code_signal_evidence") if isinstance(bundle.get("code_signal_evidence"), dict) else {}
            code["risk_scan_method"] = "executable_source_token_aware_v1"
            code["configuration_literals_treated_as_executable"] = False
            bundle["code_signal_evidence"] = code
        return bundle, complexity

    setattr(collect_with_phase5_truth, _PATCH_MARKER, True)
    snapshot.collect_snapshot_repository_evidence = collect_with_phase5_truth
    for module in tuple(sys.modules.values()):
        name = str(getattr(module, "__name__", ""))
        if name.startswith("nico.") and getattr(module, "collect_snapshot_repository_evidence", None) is original_collect:
            setattr(module, "collect_snapshot_repository_evidence", collect_with_phase5_truth)


def _patch_semgrep_config() -> None:
    from nico import scanner_evidence_pipeline_v1 as scanner

    source = Path(__file__).resolve().parents[1] / "config" / "nico-semgrep-standard.yml"

    def external_semgrep_config(workspace: Any) -> Path:
        if not source.is_file():
            raise FileNotFoundError(f"canonical Semgrep profile is missing: {source}")
        target = workspace.root / "nico-semgrep-standard.yml"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target

    setattr(external_semgrep_config, _PATCH_MARKER, True)
    scanner._semgrep_config = external_semgrep_config


def _patch_report_assessment() -> None:
    from nico import comprehensive_report_package as base_report

    current = base_report._assessment
    if getattr(current, _PATCH_MARKER, False):
        return

    def assessment_with_phase5_truth(stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        assessment = current(stage_results)
        return reconcile_phase5_report_truth(assessment, stage_results)

    setattr(assessment_with_phase5_truth, _PATCH_MARKER, True)
    base_report._assessment = assessment_with_phase5_truth


def install_phase5_report_truth_v1() -> dict[str, Any]:
    _patch_snapshot_collection()
    _patch_semgrep_config()
    _patch_report_assessment()
    return {
        "status": "installed",
        "version": VERSION,
        "executable_code_risk_scan": True,
        "scanner_report_reconciliation": True,
        "ci_history_report_integration": True,
        "baseline_delta_section": True,
        "scores_change_only_from_retained_evidence": True,
        "unchanged_risks_remain_visible": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "BASELINE",
    "scan_files_executable_only",
    "reconcile_phase5_report_truth",
    "install_phase5_report_truth_v1",
]
