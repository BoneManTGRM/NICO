from __future__ import annotations

from functools import wraps
from html import escape
from typing import Any, Callable

from nico.decision_grade_contract_v1 import DecisionGradeContract, contract_quality_summary
from nico.decision_grade_human_evidence_v1 import (
    VERSION,
    apply_human_evidence_to_contract,
    build_human_evidence_ledger,
    human_evidence_exports,
)

_MARKER = "__nico_decision_grade_human_evidence_v1__"


def _markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "## Strategic Human Evidence",
        "",
        str(ledger.get("guardrail") or ""),
        "",
        "| Module | Status | Assurance | Reviewer | Missing evidence |",
        "|---|---|---|---|---|",
    ]
    for module in ledger.get("modules") or []:
        if not isinstance(module, dict):
            continue
        missing = [*(module.get("missing_fields") or []), *(module.get("missing_metadata") or [])]
        lines.append(
            "| {label} | {status} | {assurance} | {reviewer} | {missing} |".format(
                label=str(module.get("label") or module.get("module_id") or "Unknown").replace("|", "\\|"),
                status=str(module.get("status") or "not_assessed").replace("_", " ").title(),
                assurance=str(module.get("assurance") or "NOT ASSESSED").replace("|", "\\|"),
                reviewer=str(module.get("reviewer") or "Not supplied").replace("|", "\\|"),
                missing=", ".join(str(item) for item in missing) or "None",
            )
        )
    lines.extend(
        [
            "",
            f"Complete modules: {len(ledger.get('complete_modules') or [])}. ",
            f"Incomplete modules: {len(ledger.get('incomplete_modules') or [])}. ",
            f"Explicitly excluded modules: {len(ledger.get('excluded_modules') or [])}.",
            "",
            "Incomplete modules are not inferred from repository source and constrain Strategic assurance.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _html(ledger: dict[str, Any]) -> str:
    rows: list[str] = []
    for module in ledger.get("modules") or []:
        if not isinstance(module, dict):
            continue
        missing = [*(module.get("missing_fields") or []), *(module.get("missing_metadata") or [])]
        rows.append(
            "<tr>"
            f"<td>{escape(str(module.get('label') or module.get('module_id') or 'Unknown'))}</td>"
            f"<td>{escape(str(module.get('status') or 'not_assessed').replace('_', ' ').title())}</td>"
            f"<td>{escape(str(module.get('assurance') or 'NOT ASSESSED'))}</td>"
            f"<td>{escape(str(module.get('reviewer') or 'Not supplied'))}</td>"
            f"<td>{escape(', '.join(str(item) for item in missing) or 'None')}</td>"
            "</tr>"
        )
    return (
        '<section id="strategic-human-evidence">'
        "<h2>Strategic Human Evidence</h2>"
        f"<p>{escape(str(ledger.get('guardrail') or ''))}</p>"
        "<table><thead><tr><th>Module</th><th>Status</th><th>Assurance</th><th>Reviewer</th><th>Missing evidence</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "<p>Incomplete modules are not inferred from repository source and constrain Strategic assurance.</p>"
        "</section>"
    )


def _attach_contract(result: dict[str, Any], ledger: dict[str, Any]) -> None:
    raw = result.get("decision_grade_contract")
    if not isinstance(raw, dict):
        package = result.get("report_package")
        raw = package.get("decision_grade_contract") if isinstance(package, dict) else None
    if not isinstance(raw, dict):
        return
    try:
        contract = DecisionGradeContract.model_validate(raw)
        contract = apply_human_evidence_to_contract(contract, ledger)
    except Exception:
        return
    payload = contract.model_dump(mode="json")
    summary = contract_quality_summary(contract)
    result["decision_grade_contract"] = payload
    result["delivery_status"] = summary["readiness_status"]
    package = result.get("report_package")
    if isinstance(package, dict):
        package["decision_grade_contract"] = payload
        package["delivery_status"] = summary["readiness_status"]
        package["human_review_required"] = True
        package["client_delivery_allowed"] = False
        canonical = package.get("json")
        if isinstance(canonical, dict):
            canonical["decision_grade_contract"] = payload
            canonical["delivery_status"] = summary["readiness_status"]
            canonical["human_review_required"] = True
            canonical["client_delivery_allowed"] = False


def wrap_report_builder_with_human_evidence(delegate: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = delegate(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        identity = kwargs.get("identity") if isinstance(kwargs.get("identity"), dict) else {}
        stage_results = kwargs.get("stage_results") if isinstance(kwargs.get("stage_results"), dict) else {}
        ledger = build_human_evidence_ledger(identity=identity, stage_results=stage_results)
        exports = human_evidence_exports(ledger)
        _attach_contract(result, ledger)
        result["human_evidence"] = exports
        result["strategic_human_evidence"] = ledger
        result["human_review_required"] = True
        result["client_delivery_allowed"] = False
        package = result.get("report_package")
        if isinstance(package, dict):
            package["human_evidence"] = exports
            package["strategic_human_evidence"] = ledger
            package["qa_register_csv"] = exports["qa_register_csv"]
            package["parity_matrix_csv"] = exports["parity_matrix_csv"]
            package["stakeholder_decision_log_csv"] = exports["stakeholder_decision_log_csv"]
            package["human_evidence_intake_template_json"] = exports["intake_template_json"]
            package["markdown"] = str(package.get("markdown") or "").rstrip() + "\n\n" + _markdown(ledger)
            html = str(package.get("html") or "")
            package["html"] = html.replace("</body>", _html(ledger) + "</body>") if "</body>" in html else html + _html(ledger)
            package["human_review_required"] = True
            package["client_delivery_allowed"] = False
            canonical = package.get("json")
            if isinstance(canonical, dict):
                canonical["strategic_human_evidence"] = ledger
                canonical["human_evidence_hashes"] = exports["hashes"]
                canonical["human_review_required"] = True
                canonical["client_delivery_allowed"] = False
            quality = package.get("quality") if isinstance(package.get("quality"), dict) else {}
            quality.update(
                {
                    "decision_grade_human_evidence_version": VERSION,
                    "human_evidence_ledger_present": True,
                    "human_evidence_repository_inference_allowed": False,
                    "human_evidence_incomplete_modules": len(ledger.get("incomplete_modules") or []),
                    "human_evidence_excluded_modules": len(ledger.get("excluded_modules") or []),
                    "human_evidence_client_delivery_allowed": False,
                }
            )
            package["quality"] = quality
        return result

    setattr(wrapped, _MARKER, True)
    return wrapped


def install_decision_grade_human_evidence(report_module: Any) -> dict[str, Any]:
    current = report_module.build_comprehensive_report_package
    wrapped = wrap_report_builder_with_human_evidence(current)
    report_module.build_comprehensive_report_package = wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": report_module.build_comprehensive_report_package is wrapped,
        "module_count": 10,
        "repository_inference_allowed": False,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_decision_grade_human_evidence",
    "wrap_report_builder_with_human_evidence",
]
