from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import zipfile
from functools import wraps
from typing import Any, Callable, Iterable, Mapping

VERSION = "nico.decision_grade_premium_delivery.v1"
_MARKER = "__nico_decision_grade_premium_delivery_v1__"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _text(value: Any, limit: int = 4000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[:limit]


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _csv_bytes(rows: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(fields),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                field: (
                    json.dumps(row.get(field), sort_keys=True, ensure_ascii=False, default=str)
                    if isinstance(row.get(field), (dict, list))
                    else _text(row.get(field), 12000)
                )
                for field in fields
            }
        )
    return buffer.getvalue().encode("utf-8")


def _pdf_slice(pdf_bytes: bytes, start: int, stop: int | None = None) -> bytes:
    if not pdf_bytes.startswith(b"%PDF"):
        return b""
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(pdf_bytes))
        end = len(reader.pages) if stop is None else min(len(reader.pages), max(start, stop))
        if start < 0 or start >= end:
            return b""
        writer = PdfWriter()
        for index in range(start, end):
            writer.add_page(reader.pages[index])
        writer.add_metadata(
            {
                "/Title": "NICO decision-grade report artifact",
                "/Author": "NICO",
                "/Producer": "NICO deterministic delivery package",
            }
        )
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()
    except Exception:
        return b""


def _risk_rows(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    risks = _rows(canonical.get("executive_risk_register"))
    return [
        {
            "finding_id": item.get("finding_id") or item.get("id"),
            "priority": item.get("priority"),
            "title": item.get("title"),
            "risk": item.get("risk") or item.get("impact"),
            "business_consequence": item.get("business_consequence") or item.get("business_impact"),
            "owner_role": item.get("owner_role") or item.get("owner"),
            "mitigation": item.get("mitigation") or item.get("recommendation"),
            "cost_of_inaction": item.get("cost_of_inaction"),
            "residual_risk": item.get("residual_risk"),
        }
        for item in risks
    ]


def _roadmap_rows(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for window in _rows(canonical.get("roadmap")):
        for package in _rows(window.get("work_packages")):
            output.append(
                {
                    "window": window.get("window"),
                    "objective": window.get("objective"),
                    "title": package.get("title"),
                    "priority": package.get("priority"),
                    "owner_role": package.get("owner_role") or package.get("owner"),
                    "effort_range": package.get("effort_range") or package.get("effort"),
                    "dependencies": package.get("dependencies"),
                    "acceptance_criteria": package.get("acceptance_criteria") or package.get("acceptance"),
                    "expected_technical_impact": package.get("expected_technical_impact") or package.get("expected_impact"),
                    "expected_business_impact": package.get("expected_business_impact"),
                }
            )
    return output


def _staffing_rows(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows(canonical.get("staffing_plan"))
    return [
        {
            "role": item.get("role") or item.get("owner_role"),
            "sequence": item.get("sequence") or item.get("phase"),
            "capacity_assumption": item.get("capacity_assumption") or item.get("capacity"),
            "rationale": item.get("rationale"),
            "responsibilities": item.get("responsibilities"),
            "dependencies": item.get("dependencies"),
        }
        for item in rows
    ]


def _score_ledger(canonical: dict[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    sections = _rows(assessment.get("sections"))
    return {
        "artifact_schema": VERSION,
        "maturity_signal": assessment.get("maturity_signal") or {},
        "scoring_weights": canonical.get("scoring_weights") or assessment.get("scoring_weights") or [],
        "controls": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "technical_score": item.get("score_value", item.get("presented_score", item.get("score"))),
                "technical_band": item.get("score_band_label") or item.get("score_band"),
                "evidence_assurance": item.get("assurance_label") or item.get("assurance_status"),
                "risk_disposition": item.get("risk_disposition"),
                "status": item.get("status"),
                "excluded_from_maturity": item.get("exclude_from_maturity") is True,
            }
            for item in sections
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _ci_ledger(canonical: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), dict) else {}
    return {
        "artifact_schema": VERSION,
        "ci_reliability": package.get("ci_reliability")
        or canonical.get("ci_reliability")
        or assessment.get("ci_reliability")
        or {},
        "classification_required": True,
        "expected_cancellations_are_not_code_failures": True,
        "unknown_non_success_is_not_silently_classified": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _approval_record(package: dict[str, Any]) -> dict[str, Any]:
    candidate = package.get("accepted_edition")
    if isinstance(candidate, Mapping):
        return dict(candidate)
    return {
        "artifact_schema": "nico.approval_record.pending.v1",
        "status": "pending_human_approval",
        "decision": "pending",
        "reviewer": "",
        "reviewer_role": "",
        "decision_reason": "",
        "accepted_edition": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _supply_chain(package: dict[str, Any]) -> dict[str, Any]:
    candidate = package.get("supply_chain_evidence")
    if isinstance(candidate, Mapping):
        return dict(candidate)
    return {
        "artifact_schema": "nico.decision_grade_supply_chain.unavailable.v1",
        "status": "not_assessed",
        "sbom": {},
        "dependency_inventory": [],
        "license_register": [],
        "vulnerability_register": [],
        "limitations": [
            "Supply-chain evidence was not attached to this report boundary."
        ],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _manifest_entry(name: str, payload: bytes, content_type: str) -> dict[str, Any]:
    return {
        "path": name,
        "content_type": content_type,
        "size_bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _zip(entries: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 3
            archive.writestr(info, entries[name])
    return buffer.getvalue()


def build_premium_delivery_package(report_package: Mapping[str, Any]) -> dict[str, Any]:
    package = dict(report_package)
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), dict) else {}
    report_id = _text(package.get("report_id") or canonical.get("report_id") or identity.get("run_id"), 180)
    repository = _text(identity.get("repository") or canonical.get("repository"), 260)
    run_id = _text(identity.get("run_id") or report_id, 180)
    language = _text(identity.get("report_language") or canonical.get("report_language") or "en", 40)
    depth = _text(identity.get("assessment_depth") or canonical.get("assessment_depth") or "strategic", 80)

    try:
        full_pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
    except Exception:
        full_pdf = b""
    page_count = int(package.get("pdf_page_count") or 0)
    core_pages = int(package.get("core_report_page_count") or 0)
    executive_pdf = _pdf_slice(full_pdf, 0, min(page_count or 2, 2))
    appendix_pdf = _pdf_slice(full_pdf, core_pages, None) if core_pages > 0 else b""

    findings = _rows(canonical.get("findings_register"))
    risk_rows = _risk_rows(canonical)
    roadmap_rows = _roadmap_rows(canonical)
    staffing_rows = _staffing_rows(canonical)
    supply_chain = _supply_chain(package)
    approval = _approval_record(package)
    accepted = approval.get("accepted_edition") is True and approval.get("client_delivery_allowed") is True

    entries: dict[str, bytes] = {}
    if executive_pdf:
        entries["01_executive_decision_report.pdf"] = executive_pdf
    if full_pdf:
        entries["02_detailed_technical_assessment.pdf"] = full_pdf
    if appendix_pdf:
        entries["03_evidence_appendix.pdf"] = appendix_pdf
    entries["04_findings_register.csv"] = str(package.get("findings_csv") or "").encode("utf-8")
    entries["05_findings_register.json"] = _json_bytes(findings)
    backlog_csv = package.get("jira_csv") or package.get("linear_csv") or ""
    entries["06_remediation_backlog.csv"] = str(backlog_csv).encode("utf-8")
    entries["07_risk_register.csv"] = _csv_bytes(
        risk_rows,
        (
            "finding_id",
            "priority",
            "title",
            "risk",
            "business_consequence",
            "owner_role",
            "mitigation",
            "cost_of_inaction",
            "residual_risk",
        ),
    )
    entries["08_roadmap_30_60_90.csv"] = _csv_bytes(
        [row for row in roadmap_rows if str(row.get("window")) in {"0-30 days", "31-90 days"}],
        (
            "window",
            "objective",
            "title",
            "priority",
            "owner_role",
            "effort_range",
            "dependencies",
            "acceptance_criteria",
            "expected_technical_impact",
            "expected_business_impact",
        ),
    )
    entries["09_six_month_roadmap.csv"] = _csv_bytes(
        roadmap_rows,
        (
            "window",
            "objective",
            "title",
            "priority",
            "owner_role",
            "effort_range",
            "dependencies",
            "acceptance_criteria",
            "expected_technical_impact",
            "expected_business_impact",
        ),
    )
    entries["10_resourcing_plan.csv"] = _csv_bytes(
        staffing_rows,
        (
            "role",
            "sequence",
            "capacity_assumption",
            "rationale",
            "responsibilities",
            "dependencies",
        ),
    )
    entries["12_score_and_assurance_ledger.json"] = _json_bytes(_score_ledger(canonical))
    entries["13_sbom.json"] = _json_bytes(supply_chain.get("sbom") or supply_chain)
    entries["14_ci_run_classification.json"] = _json_bytes(_ci_ledger(canonical, package))
    entries["15_approval_record.json"] = _json_bytes(approval)
    entries["16_executive_review_slides_NOT_GENERATED.json"] = _json_bytes(
        {
            "status": "not_generated",
            "reason": "Executive slides are optional and must be requested for this exact accepted edition.",
            "report_id": report_id,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )

    required_paths = {
        "01_executive_decision_report.pdf",
        "02_detailed_technical_assessment.pdf",
        "04_findings_register.csv",
        "05_findings_register.json",
        "06_remediation_backlog.csv",
        "07_risk_register.csv",
        "08_roadmap_30_60_90.csv",
        "09_six_month_roadmap.csv",
        "10_resourcing_plan.csv",
        "12_score_and_assurance_ledger.json",
        "13_sbom.json",
        "14_ci_run_classification.json",
        "15_approval_record.json",
    }
    missing = sorted(path for path in required_paths if not entries.get(path))
    artifact_manifest = {
        "artifact_schema": VERSION,
        "report_id": report_id,
        "repository": repository,
        "run_id": run_id,
        "report_language": language,
        "assessment_depth": depth,
        "delivery_status": "approved_for_delivery" if accepted and not missing else "internal_review_package",
        "artifacts": [
            _manifest_entry(
                name,
                payload,
                "application/pdf"
                if name.endswith(".pdf")
                else "text/csv"
                if name.endswith(".csv")
                else "application/json",
            )
            for name, payload in sorted(entries.items())
        ],
        "missing_required_artifacts": missing,
        "optional_slides_generated": False,
        "language_parity": {
            "current_language": language,
            "required_languages": ["en", "es-MX"],
            "equivalent_bilingual_package_verified": False,
            "status": "pending_translation_and_parity_verification",
        },
        "human_review_required": True,
        "client_delivery_allowed": bool(accepted and not missing),
    }
    entries["11_evidence_manifest.json"] = _json_bytes(artifact_manifest)
    archive = _zip(entries)
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", repository).strip("-") or "repository"
    filename = f"nico-strategic-delivery-{safe_repo}-{run_id}-{'APPROVED' if accepted and not missing else 'INTERNAL-REVIEW'}.zip"
    return {
        "artifact_schema": VERSION,
        "status": "approved_for_delivery" if accepted and not missing else "internal_review_ready" if not missing else "partial",
        "report_id": report_id,
        "filename": filename,
        "zip_base64": base64.b64encode(archive).decode("ascii"),
        "zip_sha256": _sha256(archive),
        "zip_size_bytes": len(archive),
        "artifact_count": len(entries),
        "manifest": artifact_manifest,
        "missing_required_artifacts": missing,
        "human_review_required": True,
        "client_delivery_allowed": bool(accepted and not missing),
    }


def wrap_report_builder_with_premium_delivery_package(
    delegate: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = delegate(*args, **kwargs)
        if not isinstance(result, dict):
            return result
        package = result.get("report_package")
        if not isinstance(package, dict):
            return result
        delivery = build_premium_delivery_package(package)
        package["premium_delivery_package"] = delivery
        package["delivery_package_zip_base64"] = delivery["zip_base64"]
        package["delivery_package_filename"] = delivery["filename"]
        package["delivery_package_sha256"] = delivery["zip_sha256"]
        package["delivery_package_manifest"] = delivery["manifest"]
        package["human_review_required"] = True
        package["client_delivery_allowed"] = delivery["client_delivery_allowed"]
        canonical = package.get("json")
        if isinstance(canonical, dict):
            canonical["premium_delivery_package_manifest"] = delivery["manifest"]
            canonical["human_review_required"] = True
            canonical["client_delivery_allowed"] = delivery["client_delivery_allowed"]
        result["premium_delivery_package"] = delivery
        result["report_package"] = package
        result["human_review_required"] = True
        result["client_delivery_allowed"] = delivery["client_delivery_allowed"]
        return result

    setattr(wrapped, _MARKER, True)
    return wrapped


__all__ = [
    "VERSION",
    "build_premium_delivery_package",
    "wrap_report_builder_with_premium_delivery_package",
]
