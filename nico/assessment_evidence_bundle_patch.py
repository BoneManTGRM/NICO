from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Callable

from nico.scanner_worker_orchestration import stable_artifact_hash

SCHEMA = "nico.assessment_evidence_bundle.v1"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _assessment_id(result: dict[str, Any]) -> str:
    explicit = result.get("assessment_id") or result.get("scan_id") or result.get("audit_scan_id")
    if explicit:
        return str(explicit)
    basis = {
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "assessment_mode": result.get("assessment_mode"),
        "timeframe_days": result.get("timeframe_days"),
    }
    return stable_artifact_hash(basis)[:16]


def _scanner_tools(result: dict[str, Any]) -> list[dict[str, Any]]:
    worker = _safe_dict(result.get("scanner_worker_artifact"))
    orchestration = _safe_dict(worker.get("orchestration"))
    orchestrated_tools = orchestration.get("tools") if isinstance(orchestration.get("tools"), list) else []
    if orchestrated_tools:
        return deepcopy(orchestrated_tools)

    tools = worker.get("tools") if isinstance(worker.get("tools"), dict) else {}
    rows: list[dict[str, Any]] = []
    for name, payload in sorted(tools.items()):
        payload = payload if isinstance(payload, dict) else {}
        findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
        rows.append(
            {
                "tool": str(name),
                "category": payload.get("category") or "unknown",
                "status": payload.get("status") or "unknown",
                "exit_code": payload.get("returncode"),
                "timed_out": bool(payload.get("timed_out")),
                "finding_count": len(findings),
                "artifact_hash": stable_artifact_hash(payload),
            }
        )
    return rows


def _tool_groups(tools: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[str]] = {}
    for item in tools:
        category = str(item.get("category") or "unknown")
        by_category.setdefault(category, []).append(str(item.get("tool") or "unknown"))
    return {
        "dependency": by_category.get("dependency", []),
        "static": by_category.get("static", []),
        "secret": by_category.get("secret", []),
        "coverage": by_category.get("coverage", []),
        "unknown": by_category.get("unknown", []),
    }


def _section_references(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in _safe_list(result.get("sections")):
        if not isinstance(section, dict):
            continue
        evidence = _safe_list(section.get("evidence"))
        findings = _safe_list(section.get("findings"))
        unavailable = _safe_list(section.get("unavailable"))
        rows.append(
            {
                "section_id": section.get("id"),
                "label": section.get("label"),
                "status": section.get("status"),
                "score": section.get("score"),
                "evidence_count": len(evidence),
                "finding_count": len(findings),
                "unavailable_count": len(unavailable),
                "section_hash": stable_artifact_hash(
                    {
                        "id": section.get("id"),
                        "evidence": evidence,
                        "findings": findings,
                        "unavailable": unavailable,
                    }
                ),
            }
        )
    return rows


def build_assessment_evidence_bundle(result: dict[str, Any], evidence_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build one normalized attachment contract for scanner, CI, complexity, and report evidence."""
    evidence_bundle = _safe_dict(evidence_bundle)
    worker = _safe_dict(result.get("scanner_worker_artifact"))
    orchestration = _safe_dict(worker.get("orchestration"))
    tools = _scanner_tools(result)
    ledger = _safe_dict(result.get("evidence_ledger") or evidence_bundle.get("evidence_ledger"))
    complexity_summary = _safe_dict(result.get("complexity_engine_summary"))
    complexity_engine = _safe_dict(result.get("complexity_engine"))
    secret_history = _safe_dict(result.get("secret_history_scan"))
    bundle = {
        "artifact_schema": SCHEMA,
        "assessment_id": _assessment_id(result),
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "human_review_required": bool(result.get("human_review_required", True)),
        "scanner_worker": {
            "run_id": worker.get("run_id") or orchestration.get("run_id"),
            "state": worker.get("worker_execution_state"),
            "artifact_hash": worker.get("artifact_hash") or stable_artifact_hash(worker) if worker else None,
            "orchestration_hash": orchestration.get("manifest_hash"),
            "tool_count": len(tools),
            "completed_tools": orchestration.get("completed_tools") or [item.get("tool") for item in tools if item.get("status") == "completed"],
            "unavailable_tools": orchestration.get("unavailable_tools") or [item.get("tool") for item in tools if item.get("status") in {"unavailable", "missing"}],
            "finding_tools": orchestration.get("finding_tools") or [item.get("tool") for item in tools if item.get("has_findings") or item.get("finding_count")],
        },
        "tool_groups": _tool_groups(tools),
        "tools": tools,
        "complexity": {
            "summary_attached": bool(complexity_summary),
            "engine_attached": bool(complexity_engine),
            "summary_hash": stable_artifact_hash(complexity_summary) if complexity_summary else None,
            "engine_hash": stable_artifact_hash(complexity_engine) if complexity_engine else None,
        },
        "secrets": {
            "history_scan_attached": bool(secret_history),
            "history_aware": bool(secret_history.get("history_aware")),
            "completed_tools": secret_history.get("completed_tools") if isinstance(secret_history.get("completed_tools"), list) else [],
            "secret_history_hash": stable_artifact_hash(secret_history) if secret_history else None,
        },
        "ci": {
            "references": deepcopy(evidence_bundle.get("ci_references") if isinstance(evidence_bundle.get("ci_references"), list) else []),
        },
        "sections": _section_references(result),
        "evidence_ledger": {
            "attached": bool(ledger),
            "entry_count": ledger.get("entry_count"),
            "ledger_hash": ledger.get("ledger_hash"),
        },
        "source_bundle_hash": evidence_bundle.get("bundle_hash"),
        "guardrail": "This bundle normalizes attached evidence only. Missing tools, unavailable artifacts, findings, and human-review requirements remain explicit and do not become clean proof.",
    }
    bundle["bundle_hash"] = stable_artifact_hash({key: value for key, value in bundle.items() if key != "bundle_hash"})
    return bundle


def attach_assessment_evidence_bundle(result: dict[str, Any]) -> dict[str, Any]:
    output = result
    existing = _safe_dict(output.get("evidence_artifact_bundle"))
    normalized = build_assessment_evidence_bundle(output, existing)
    output["assessment_evidence_bundle"] = normalized
    if existing:
        existing["assessment_evidence_bundle"] = normalized
        existing.setdefault("artifacts", {})["assessment_evidence_bundle_json"] = {
            "filename": "assessment-evidence-bundle.json",
            "available": True,
            "sha256": stable_artifact_hash(normalized),
        }
        existing["bundle_hash"] = stable_artifact_hash({key: value for key, value in existing.items() if key != "bundle_hash"})
    reports = output.setdefault("reports", {})
    reports["assessment_evidence_bundle_json"] = json.dumps(normalized, indent=2, sort_keys=True, default=str)
    reports["assessment_evidence_bundle_filename"] = f"nico-assessment-evidence-{str(output.get('repository') or 'assessment').replace('/', '-')}.json"
    return output


def install_assessment_evidence_bundle_patch() -> None:
    from nico import evidence_artifact_bundle as bundle_module

    original_build: Callable[..., dict[str, Any]] | None = getattr(bundle_module, "_nico_original_build_evidence_artifact_bundle_assessment_bundle", None)
    if original_build is None:
        original_build = bundle_module.build_evidence_artifact_bundle
        bundle_module._nico_original_build_evidence_artifact_bundle_assessment_bundle = original_build

    def build_evidence_artifact_bundle_with_assessment_bundle(result: dict[str, Any]) -> dict[str, Any]:
        base = original_build(result)
        normalized = build_assessment_evidence_bundle(result, base)
        base["assessment_evidence_bundle"] = normalized
        base.setdefault("artifacts", {})["assessment_evidence_bundle_json"] = {
            "filename": "assessment-evidence-bundle.json",
            "available": True,
            "sha256": stable_artifact_hash(normalized),
        }
        base["bundle_hash"] = stable_artifact_hash({key: value for key, value in base.items() if key != "bundle_hash"})
        return base

    bundle_module.build_evidence_artifact_bundle = build_evidence_artifact_bundle_with_assessment_bundle

    original_attach: Callable[..., dict[str, Any]] | None = getattr(bundle_module, "_nico_original_attach_evidence_artifact_bundle_assessment_bundle", None)
    if original_attach is None:
        original_attach = bundle_module.attach_evidence_artifact_bundle
        bundle_module._nico_original_attach_evidence_artifact_bundle_assessment_bundle = original_attach

    def attach_evidence_artifact_bundle_with_assessment_bundle(result: dict[str, Any]) -> dict[str, Any]:
        output = original_attach(result)
        return attach_assessment_evidence_bundle(output)

    bundle_module.attach_evidence_artifact_bundle = attach_evidence_artifact_bundle_with_assessment_bundle
