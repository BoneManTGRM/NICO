from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


FINAL_REVIEW_SCHEMA = "nico.client_final_review_gate.v1"
REQUIRED_REVIEW_ROLES = (
    "technical_reviewer",
    "delivery_owner",
    "client_or_authorized_representative",
)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _artifact_available(bundle: dict[str, Any], name: str) -> bool:
    artifacts = _safe_dict(bundle.get("artifacts"))
    item = _safe_dict(artifacts.get(name))
    return bool(item.get("available") and item.get("sha256"))


def _reports(result: dict[str, Any]) -> dict[str, Any]:
    return _safe_dict(result.get("reports"))


def _evidence_bundle(result: dict[str, Any]) -> dict[str, Any]:
    return _safe_dict(result.get("evidence_artifact_bundle"))


def _evidence_ledger(result: dict[str, Any]) -> dict[str, Any]:
    bundle = _evidence_bundle(result)
    return _safe_dict(result.get("evidence_ledger")) or _safe_dict(bundle.get("evidence_ledger"))


def _report_full_detail(result: dict[str, Any]) -> dict[str, Any]:
    return _safe_dict(result.get("report_full_detail_export"))


def _client_gate(result: dict[str, Any]) -> dict[str, Any]:
    return _safe_dict(result.get("client_acceptance"))


def build_client_final_review_gate(result: dict[str, Any]) -> dict[str, Any]:
    bundle = _evidence_bundle(result)
    ledger = _evidence_ledger(result)
    reports = _reports(result)
    full_detail = _report_full_detail(result)
    client_gate = _client_gate(result)
    disclosures = _safe_dict(client_gate.get("disclosures"))
    unavailable_count = int(disclosures.get("unavailable_count") or ledger.get("unavailable_entry_count") or 0)
    finding_count = int(disclosures.get("finding_count") or ledger.get("finding_entry_count") or len(_safe_list(result.get("findings"))))

    checks = [
        ("client_acceptance_gate_present", bool(client_gate), "Client acceptance gate exists."),
        ("evidence_bundle_hash_present", bool(bundle.get("bundle_hash")), "Evidence bundle hash exists."),
        ("evidence_ledger_hash_present", bool(ledger.get("ledger_hash")), "Evidence ledger hash exists."),
        ("markdown_export_hashed", _artifact_available(bundle, "markdown"), "Markdown export hash exists."),
        ("html_export_hashed", _artifact_available(bundle, "html"), "HTML export hash exists."),
        ("raw_evidence_hashed", _artifact_available(bundle, "raw_evidence_json"), "Raw evidence JSON hash exists."),
        ("unavailable_inventory_hashed", _artifact_available(bundle, "unavailable_inventory_json"), "Unavailable inventory hash exists."),
        ("full_detail_export_present", bool(full_detail.get("artifact_schema") == "nico.report_full_detail.v1" or reports.get("full_detail_json")), "Full-detail export exists."),
        ("human_review_explicit", bool(result.get("human_review_required", True)), "Human review remains explicit."),
        ("sections_present", bool(_safe_list(result.get("sections"))), "Report sections are present."),
    ]

    checklist = []
    blockers = []
    for check_id, passed, label in checks:
        checklist.append({"id": check_id, "passed": bool(passed), "label": label})
        if not passed:
            blockers.append(label)

    disclosure_state = "clean" if unavailable_count == 0 and finding_count == 0 else "disclosures_present"
    if blockers:
        status = "blocked_missing_final_review_evidence"
    elif disclosure_state == "disclosures_present":
        status = "ready_for_final_human_review_with_disclosures"
    else:
        status = "ready_for_final_human_review"

    return {
        "artifact_schema": FINAL_REVIEW_SCHEMA,
        "status": status,
        "client_delivery_allowed": False,
        "automation_finality": "not_final",
        "disclosure_state": disclosure_state,
        "unavailable_count": unavailable_count,
        "finding_count": finding_count,
        "required_review_roles": [
            {"role": role, "required": True, "status": "pending"}
            for role in REQUIRED_REVIEW_ROLES
        ],
        "checklist": checklist,
        "blockers": blockers,
        "evidence_bundle_hash": bundle.get("bundle_hash") or "",
        "evidence_ledger_hash": ledger.get("ledger_hash") or "",
        "full_detail_filename": reports.get("full_detail_filename") or "",
        "evidence_ledger_filename": reports.get("evidence_ledger_filename") or "",
        "rule": "Client-facing delivery remains blocked until required final human review and client acceptance signoffs are explicitly approved.",
        "guardrail": "This gate does not certify quality automatically. It only verifies that final report evidence, disclosures, hashes, and human-review requirements are attached before signoff.",
    }


def attach_client_final_review_gate(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("status") != "complete":
        return result
    output = result
    final_gate = build_client_final_review_gate(output)
    output["client_final_review_gate"] = final_gate
    output["human_review_required"] = True
    client_gate = _safe_dict(output.get("client_acceptance"))
    if client_gate:
        client_gate["final_review_gate"] = deepcopy(final_gate)
        client_gate["client_delivery_allowed"] = False
        client_gate["automation_finality"] = "not_final"
        output["client_acceptance"] = client_gate
    return output


def _patch_client_acceptance_attachment() -> None:
    from nico import client_acceptance

    original: Callable[[dict[str, Any]], dict[str, Any]] | None = getattr(client_acceptance, "_nico_original_attach_client_acceptance_gate_final_review", None)
    if original is None:
        original = client_acceptance.attach_client_acceptance_gate
        client_acceptance._nico_original_attach_client_acceptance_gate_final_review = original

    def attach_client_acceptance_gate_with_final_review(result: dict[str, Any]) -> dict[str, Any]:
        original_func = client_acceptance._nico_original_attach_client_acceptance_gate_final_review
        return attach_client_final_review_gate(original_func(result))

    client_acceptance.attach_client_acceptance_gate = attach_client_acceptance_gate_with_final_review


def _patch_client_acceptance_status() -> None:
    from nico import client_acceptance

    original: Callable[..., dict[str, Any]] | None = getattr(client_acceptance, "_nico_original_client_acceptance_status_final_review", None)
    if original is None:
        original = client_acceptance.client_acceptance_status
        client_acceptance._nico_original_client_acceptance_status_final_review = original

    def client_acceptance_status_with_final_review(*args: Any, **kwargs: Any) -> dict[str, Any]:
        status = client_acceptance._nico_original_client_acceptance_status_final_review(*args, **kwargs)
        gate = _safe_dict(status.get("client_acceptance"))
        final_gate = _safe_dict(gate.get("final_review_gate"))
        if final_gate:
            status["client_final_review_gate"] = final_gate
            if status.get("client_delivery_allowed") and final_gate.get("blockers"):
                status["client_delivery_allowed"] = False
                status["acceptance_status"] = "blocked_missing_final_review_evidence"
        return status

    client_acceptance.client_acceptance_status = client_acceptance_status_with_final_review


def install_client_final_review_gate_patch() -> None:
    _patch_client_acceptance_attachment()
    _patch_client_acceptance_status()
