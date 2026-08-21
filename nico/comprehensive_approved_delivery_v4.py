from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico.comprehensive_approved_delivery_v1 import require_new_report_after_evidence_request
from nico.comprehensive_approved_delivery_v3 import (
    build_approved_delivery_package as build_v3,
    validate_approved_delivery_package as validate_v3,
)
from nico.comprehensive_client_delivery_contract_v1 import (
    CLIENT_FINAL_CLASSIFICATION,
    PRODUCT_NAME,
    VERSION as CONTRACT_VERSION,
    build_approval_receipt,
    canonical_sha256,
    engagement_binding,
    validate_approval_receipt,
    version_truth,
)

VERSION = "nico.comprehensive_approved_delivery.v4"
_RECEIPT_PATH = "12_phase4_approval_receipt.json"
_MANIFEST_PATH = "11_evidence_manifest.json"


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _review_metadata(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    value = manifest.get("review")
    return value if isinstance(value, Mapping) else {}


def _bounded_validation_error_code(exc: ValueError) -> str:
    raw = _text(exc).split(":", 1)[0]
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_"
        for char in raw
    )[:120]
    return normalized or "value_error"


def _receipt_validation_record(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Use the accepted edition's frozen operational-history reference.

    Attaching the approved package legitimately recomputes the enclosing run-record
    integrity hash. That bookkeeping change must not invalidate the exact receipt it
    just enclosed. All material report, evidence, candidate, disposition, identity,
    and version fields are still rebuilt from the current record.
    """

    output = deepcopy(dict(record))
    binding = manifest.get("phase4_approval_binding")
    if not isinstance(binding, Mapping):
        return output
    truth = binding.get("version_truth")
    if not isinstance(truth, Mapping):
        return output
    frozen = _text(truth.get("mutable_operational_history_reference"))
    if not frozen:
        return output
    output.pop("audit_chain_sha256", None)
    output["integrity_sha256"] = frozen
    return output


def bind_phase4_approval_manifest(
    record: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Retain client/project/authorization/version truth in the accepted edition.

    The existing report artifacts remain untouched. The accepted-edition certificate
    is recomputed because the Phase 4 identity binding is itself approval evidence.
    """

    output = deepcopy(dict(manifest))
    review = deepcopy(dict(_review_metadata(output)))
    binding = engagement_binding(record)
    decision = _text(review.get("decision")).casefold()
    reviewer = _text(review.get("reviewer"))
    reviewer_role = _text(review.get("reviewer_role"))
    reason = _text(review.get("reason"))
    decided_at = _text(review.get("decided_at"))
    if decision == "approved":
        # build_approval_receipt performs the authoritative human/role checks. This
        # preliminary metadata is bound before the final receipt is generated.
        from nico.comprehensive_client_delivery_contract_v1 import reviewer_binding

        human = reviewer_binding(
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision=decision,
            decided_at=decided_at,
            decision_reason=reason,
        )
    else:
        human = {
            "reviewer_identity": reviewer,
            "reviewer_role": reviewer_role,
            "authorization_basis": "protected_admin_write_and_explicit_review_authorization",
            "review_decision": decision,
            "review_timestamp": decided_at,
            "residual_risk_decision": "not_accepted",
            "reviewer_notes": reason,
            "human_action_required": True,
            "automation_may_not_approve": True,
            "approval_record_id": "approval_" + canonical_sha256(review)[:24],
        }
    phase4_binding = {
        "artifact_schema": CONTRACT_VERSION,
        "product_name": PRODUCT_NAME,
        "package_classification": CLIENT_FINAL_CLASSIFICATION,
        "client_identity": binding["client_identity"],
        "project_identity": binding["project_identity"],
        "customer_id": binding["customer_id"],
        "client_id": binding["client_id"],
        "project_id": binding["project_id"],
        "authorized_scope": binding["authorized_scope"],
        "read_only_access_method": binding["access_method"],
        "review": human,
        "version_truth": version_truth(record),
        "one_product": PRODUCT_NAME,
        "one_client_report": True,
        "human_review_required": True,
        "client_delivery_allowed": decision == "approved" and output.get("accepted_edition") is True,
    }
    phase4_binding["binding_sha256"] = canonical_sha256(phase4_binding)
    output["phase4_approval_binding"] = phase4_binding
    output["client_identity"] = binding["client_identity"]
    output["project_identity"] = binding["project_identity"]
    output["customer_id"] = binding["customer_id"]
    output["client_id"] = binding["client_id"]
    output["project_id"] = binding["project_id"]
    output["package_classification"] = CLIENT_FINAL_CLASSIFICATION
    output["one_product"] = PRODUCT_NAME
    output["one_client_report"] = True

    review.pop("approval_certificate_sha256", None)
    review["authorization_basis"] = human["authorization_basis"]
    review["residual_risk_decision"] = human["residual_risk_decision"]
    review["approval_record_id"] = human["approval_record_id"]
    review["approval_certificate_sha256"] = canonical_sha256(review)
    output["review"] = review
    output.pop("accepted_edition_manifest_sha256", None)
    output["accepted_edition_manifest_sha256"] = canonical_sha256(output)
    return output


def _enhance_delivery_archive(
    delivery: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any], str]:
    try:
        source = base64.b64decode(_text(delivery.get("zip_base64")), validate=True)
    except Exception as exc:
        raise ValueError("phase4_delivery_zip_invalid") from exc
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(source), "r") as archive:
        for name in archive.namelist():
            if not name.endswith("/"):
                entries[name] = archive.read(name)
    receipt_bytes = _json_bytes(receipt)
    entries[_RECEIPT_PATH] = receipt_bytes

    manifest = deepcopy(dict(delivery.ge²È="24}Í¡„ÈÔØ¡…É¡¥Ù”¤(€€€•ÉÑ¥™¥…Ñ•l‰‘•±¥Ù•Éå}Á…­…•}Í¥é•}‰åÑ•Ì‰t€ô±•¸¡…É¡¥Ù”¤(€€€•ÉÑ¥™¥…Ñ”¹Á½À ‰‘•±¥Ù•Éå}…ÕÑ¡½É¥é…Ñ¥½¹}•ÉÑ¥™¥…Ñ•}Í¡„ÈÔØˆ°9½¹”¤(€€€•ÉÑ¥™¥…Ñ•l‰‘•±¥Ù•Éå}…ÕÑ¡½É¥é…Ñ¥½¹}•ÉÑ¥™¥…Ñ•}Í¡„ÈÔØ‰t€ô…¹½¹¥…±}Í¡„ÈÔØ¡•ÉÑ¥™¥…Ñ”¤(€€€É•ÑÕÉ¸ì(€€€€€€€€¨©‘¥Ð¡‘•±¥Ù•Éä¤°(€€€€€€€€‰…ÉÑ¥™…Ñ}Í¡•µ„ˆèYIM%=8°(€€€€€€€€‰é¥Á}‰…Í”ØÐˆè‰…Í”ØÐ¹ˆØÑ•¹½‘”¡…É¡¥Ù”¤¹‘•½‘” ‰…Í¥¤ˆ¤°(€€€€€€€€‰é¥Á}Í¡„ÈÔØˆè}Í¡„ÈÔØ¡…É¡¥Ù”¤°(€€€€€€€€‰é¥Á}Í¥é•}‰åÑ•Ìˆè±•¸¡…É¡¥Ù”¤°(€€€€€€€€‰…ÉÑ¥™…Ñ}½Õ¹Ðˆè±•¸¡‘•±¥Ù•Éå}µ…¹¥™•ÍÐ¹•Ð ‰…ÉÑ¥™…ÑÌˆ¤½Èmt¤°(€€€€€€€€‰µ…¹¥™•ÍÐˆè‘•±¥Ù•Éå}µ…¹¥™•ÍÐ°(€€€€€€€€‰•ÉÑ¥™¥…Ñ”ˆè•ÉÑ¥™¥…Ñ”°(€€€€€€€€‰Á¡…Í”Ñ}…ÁÁÉ½Ù…±}É••¥ÁÐˆèÉ••¥ÁÐ°(€€€€€€€€‰Á¡…Í”Ñ}…ÁÁÉ½Ù…±}É••¥ÁÑ}Í¡„ÈÔØˆèÉ••¥ÁÑl‰…ÁÁÉ½Ù…±}É••¥ÁÑ}Í¡„ÈÔØ‰t°(€€€€€€€€‰ÁÉ½‘ÕÑ}¹…µ”ˆèAI=UQ}95°(€€€€€€€€‰Á…­…•}±…ÍÍ¥™¥…Ñ¥½¸ˆè1%9Q}%91}1MM%%Q%=8°(€€€€€€€€‰½¹•}±¥•¹Ñ}É•Á½ÉÐˆèQÉÕ”°(€€€€€€€€‰±¥•¹Ñ}Á‘™}½Õ¹Ðˆè€Ä°(€€€€€€€€‰¡Õµ…¹}É•Ù¥•Ý}É•ÅÕ¥É•ˆèQÉÕ”°(€€€€€€€€‰±¥•¹Ñ}‘•±¥Ù•Éå}…±±½Ý•ˆèQÉÕ”°(€€€ô(()‘•˜Ù…±¥‘…Ñ•}…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…” (€€€É•½Éè5…ÁÁ¥¹mÍÑÈ°¹åt°(€€€Á…­…”è¹ä°(¤€´ø‘¥ÑmÍÑÈ°¹åtè(€€€ÑÉäè(€€€€€€€É•ÍÕ±Ð€ô‘¥Ð¡Ù…±¥‘…Ñ•}ØÌ¡É•½É°Á…­…”¤¤(€€€€€€€•ÉÉ½ÉÌ€ôÍ•Ð¡ÍÑÈ¡¥Ñ•´¤™½È¥Ñ•´¥¸É•ÍÕ±Ð¹•Ð ‰Ù…±¥‘…Ñ¥½¹}•ÉÉ½ÉÌˆ¤½Èmt¤(€€€•á•ÁÐY…±Õ•ÉÉ½È…Ì•áŒè(€€€€€€€É•ÍÕ±Ð€ôì(€€€€€€€€€€€€‰ÍÑ…ÑÕÌˆè€‰¥¹Ù…±¥ˆ°(€€€€€€€€€€€€‰Ù…±¥‘…Ñ¥½¹}•ÉÉ½ÉÌˆèmt°(€€€€€€€€€€€€‰±¥•¹Ñ}‘•±¥Ù•Éå}…±±½Ý•ˆè…±Í”°(€€€€€€€ô(€€€€€€€•ÉÉ½ÉÌ€ôì(€€€€€€€€€€€€‰Á¡…Í”Ñ}¥¹¡•É¥Ñ•‘}Ù…±¥‘…Ñ¥½¹}™…¥±•èˆ(€€€€€€€€€€€€¬}‰½Õ¹‘•‘}Ù…±¥‘…Ñ¥½¹}•ÉÉ½É}½‘”¡•áŒ¤(€€€€€€€ô(€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡Á…­…”°5…ÁÁ¥¹œ¤è(€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}‘•±¥Ù•Éå}Á…­…•}µÕÍÑ}‰•}µ…ÁÁ¥¹œˆ¤(€€€€€€€É•ÑÕÉ¸ì(€€€€€€€€€€€€¨©É•ÍÕ±Ð°(€€€€€€€€€€€€‰ÍÑ…ÑÕÌˆè€‰¥¹Ù…±¥ˆ°(€€€€€€€€€€€€‰Ù…±¥‘…Ñ¥½¹}•ÉÉ½ÉÌˆèÍ½ÉÑ•¡•ÉÉ½ÉÌ¤°(€€€€€€€€€€€€‰±¥•¹Ñ}‘•±¥Ù•Éå}…±±½Ý•ˆè…±Í”°(€€€€€€€ô(€€€µ…¹¥™•ÍÐ€ôÉ•½É¹•Ð ‰…•ÁÑ•‘}•‘¥Ñ¥½¸ˆ¤(€€€É••¥ÁÐ€ôÁ…­…”¹•Ð ‰Á¡…Í”Ñ}…ÁÁÉ½Ù…±}É••¥ÁÐˆ¤(€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡µ…¹¥™•ÍÐ°5…ÁÁ¥¹œ¤è(€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}…•ÁÑ•‘}•‘¥Ñ¥½¹}µ¥ÍÍ¥¹œˆ¤(€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡É••¥ÁÐ°5…ÁÁ¥¹œ¤è(€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}…ÁÁÉ½Ù…±}É••¥ÁÑ}µ¥ÍÍ¥¹œˆ¤(€€€¥˜¥Í¥¹ÍÑ…¹”¡µ…¹¥™•ÍÐ°5…ÁÁ¥¹œ¤…¹¥Í¥¹ÍÑ…¹”¡É••¥ÁÐ°5…ÁÁ¥¹œ¤è(€€€€€€€Ù…±¥‘…Ñ¥½¸€ôÙ…±¥‘…Ñ•}…ÁÁÉ½Ù…±}É••¥ÁÐ (€€€€€€€€€€€}É••¥ÁÑ}Ù…±¥‘…Ñ¥½¹}É•½É¡É•½É°µ…¹¥™•ÍÐ¤°(€€€€€€€€€€€µ…¹¥™•ÍÐ°(€€€€€€€€€€€É••¥ÁÐ°(€€€€€€€€¤(€€€€€€€•ÉÉ½ÉÌ¹ÕÁ‘…Ñ”¡Ù…±¥‘…Ñ¥½¸¹•Ð ‰Ù…±¥‘…Ñ¥½¹}•ÉÉ½ÉÌˆ¤½Èmt¤(€€€¥˜}Ñ•áÐ¡Á…­…”¹•Ð ‰ÁÉ½‘ÕÑ}¹…µ”ˆ¤¤€„ôAI=UQ}95è(€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}ÝÉ½¹}ÁÉ½‘ÕÐˆ¤(€€€¥˜}Ñ•áÐ¡Á…­…”¹•Ð ‰Á…­…•}±…ÍÍ¥™¥…Ñ¥½¸ˆ¤¤€„ô1%9Q}%91}1MM%%Q%=8è(€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}¥¹Ñ•É¹…±}½É}Ñ•ÍÑ}Á…­…•}‰±½­•ˆ¤(€€€¥˜Á…­…”¹•Ð ‰½¹•}±¥•¹Ñ}É•Á½ÉÐˆ¤¥Ì¹½ÐQÉÕ”½È¥¹Ð¡Á…­…”¹•Ð ‰±¥•¹Ñ}Á‘™}½Õ¹Ðˆ¤½È€À¤€„ô€Äè(€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}½¹•}É•Á½ÉÑ}ÉÕ±•}Ù¥½±…Ñ•ˆ¤((€€€ÑÉäè(€€€€€€€…É¡¥Ù•}‰åÑ•Ì€ô‰…Í”ØÐ¹ˆØÑ‘•½‘”¡}Ñ•áÐ¡Á…­…”¹•Ð ‰é¥Á}‰…Í”ØÐˆ¤¤°Ù…±¥‘…Ñ”õQÉÕ”¤(€€€€€€€¥˜}Í¡„ÈÔØ¡…É¡¥Ù•}‰åÑ•Ì¤€„ô}Ñ•áÐ¡Á…­…”¹•Ð ‰é¥Á}Í¡„ÈÔØˆ¤¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}‘•±¥Ù•Éå}…É¡¥Ù•}¡…Í¡}µ¥Íµ…Ñ ˆ¤(€€€€€€€Ý¥Ñ é¥Á™¥±”¹i¥Á¥±”¡¥¼¹	åÑ•Í%<¡…É¡¥Ù•}‰åÑ•Ì¤°€‰Èˆ¤…Ì…É¡¥Ù”è(€€€€€€€€€€€¹…µ•Ì€ô…É¡¥Ù”¹¹…µ•±¥ÍÐ ¤(€€€€€€€€€€€Á‘™Ì€ôm¹…µ”™½È¹…µ”¥¸¹…µ•Ì¥˜¹…µ”¹…Í•™½± ¤¹•¹‘ÍÝ¥Ñ  ˆ¹Á‘˜ˆ¥t(€€€€€€€€€€€¥˜±•¸¡Á‘™Ì¤€„ô€Äè(€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}½¹•}É•Á½ÉÑ}ÉÕ±•}Ù¥½±…Ñ•ˆ¤(€€€€€€€€€€€¥˜}I%AQ}AQ ¹½Ð¥¸¹…µ•Ìè(€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}É••¥ÁÑ}¹½Ñ}¥¹}¥µµÕÑ…‰±•}Á…­…”ˆ¤(€€€€€€€€€€€•±¥˜¥Í¥¹ÍÑ…¹”¡É••¥ÁÐ°5…ÁÁ¥¹œ¤è(€€€€€€€€€€€€€€€¥˜…É¡¥Ù”¹É•…¡}I%AQ}AQ ¤€„ô}©Í½¹}‰åÑ•Ì¡É••¥ÁÐ¤è(€€€€€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}É••¥ÁÑ}…É¡¥Ù•}µ¥Íµ…Ñ ˆ¤(€€€€€€€€€€€¥˜}59%MQ}AQ ¹½Ð¥¸¹…µ•Ìè(€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}•Ù¥‘•¹•}µ…¹¥™•ÍÑ}µ¥ÍÍ¥¹œˆ¤(€€€€€€€€€€€•±Í”è(€€€€€€€€€€€€€€€µ…¹¥™•ÍÑ}Í¡„€ô}Í¡„ÈÔØ¡…É¡¥Ù”¹É•…¡}59%MQ}AQ ¤¤(€€€€€€€€€€€€€€€•ÉÑ¥™¥…Ñ”€ôÁ…­…”¹•Ð ‰•ÉÑ¥™¥…Ñ”ˆ¤(€€€€€€€€€€€€€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡•ÉÑ¥™¥…Ñ”°5…ÁÁ¥¹œ¤½È}Ñ•áÐ (€€€€€€€€€€€€€€€€€€€•ÉÑ¥™¥…Ñ”¹•Ð ‰•Ù¥‘•¹•}µ…¹¥™•ÍÑ}Í¡„ÈÔØˆ¤(€€€€€€€€€€€€€€€€¤€„ôµ…¹¥™•ÍÑ}Í¡„è(€€€€€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}•Ù¥‘•¹•}µ…¹¥™•ÍÑ}¡…Í¡}µ¥Íµ…Ñ ˆ¤(€€€•á•ÁÐá•ÁÑ¥½¸è(€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}‘•±¥Ù•Éå}…É¡¥Ù•}¥¹Ù…±¥ˆ¤((€€€•ÉÑ¥™¥…Ñ”€ôÁ…­…”¹•Ð ‰•ÉÑ¥™¥…Ñ”ˆ¤(€€€‰¥¹‘¥¹œ€ô•¹…•µ•¹Ñ}‰¥¹‘¥¹œ¡É•½É¤(€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡•ÉÑ¥™¥…Ñ”°5…ÁÁ¥¹œ¤è(€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}‘•±¥Ù•Éå}•ÉÑ¥™¥…Ñ•}µ¥ÍÍ¥¹œˆ¤(€€€•±Í”è(€€€€€€€™½È­•ä°•áÁ•Ñ•¥¸€ (€€€€€€€€€€€€ ‰±¥•¹Ñ}¥‘•¹Ñ¥Ñäˆ°‰¥¹‘¥¹l‰±¥•¹Ñ}¥‘•¹Ñ¥Ñä‰t¤°(€€€€€€€€€€€€ ‰ÁÉ½©•Ñ}¥‘•¹Ñ¥Ñäˆ°‰¥¹‘¥¹l‰ÁÉ½©•Ñ}¥‘•¹Ñ¥Ñä‰t¤°(€€€€€€€€€€€€ ‰ÁÉ½©•Ñ}¥ˆ°‰¥¹‘¥¹l‰ÁÉ½©•Ñ}¥‰t¤°(€€€€€€€€¤è(€€€€€€€€€€€¥˜}Ñ•áÐ¡•ÉÑ¥™¥…Ñ”¹•Ð¡­•ä¤¤€„ô}Ñ•áÐ¡•áÁ•Ñ•¤è(€€€€€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘¡˜‰Á¡…Í”Ñ}í­•åõ}µ¥Íµ…Ñ ˆ¤(€€€€€€€…¹‘¥‘…Ñ”€ô‘••Á½Áä¡‘¥Ð¡•ÉÑ¥™¥…Ñ”¤¤(€€€€€€€ÍÕÁÁ±¥•‘}¡…Í €ô}Ñ•áÐ¡…¹‘¥‘…Ñ”¹Á½À ‰‘•±¥Ù•Éå}…ÕÑ¡½É¥é…Ñ¥½¹}•ÉÑ¥™¥…Ñ•}Í¡„ÈÔØˆ°€ˆˆ¤¤(€€€€€€€¥˜ÍÕÁÁ±¥•‘}¡…Í €„ô…¹½¹¥…±}Í¡„ÈÔØ¡…¹‘¥‘…Ñ”¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}‘•±¥Ù•Éå}•ÉÑ¥™¥…Ñ•}¡…Í¡}µ¥Íµ…Ñ ˆ¤(€€€€€€€¥˜}Ñ•áÐ¡•ÉÑ¥™¥…Ñ”¹•Ð ‰‘•±¥Ù•Éå}Á…­…•}Í¡„ÈÔØˆ¤¤€„ô}Ñ•áÐ¡Á…­…”¹•Ð ‰é¥Á}Í¡„ÈÔØˆ¤¤è(€€€€€€€€€€€•ÉÉ½ÉÌ¹…‘ ‰Á¡…Í”Ñ}•ÉÑ¥™¥…Ñ•}…É¡¥Ù•}‰¥¹‘¥¹}µ¥Íµ…Ñ ˆ¤((€€€É•ÑÕÉ¸ì(€€€€€€€€¨©É•ÍÕ±Ð°(€€€€€€€€‰…ÉÑ¥™…Ñ}Í¡•µ„ˆèYIM%=8°(€€€€€€€€‰ÍÑ…ÑÕÌˆè€‰Ù…±¥ˆ¥˜¹½Ð•ÉÉ½ÉÌ•±Í”€‰¥¹Ù…±¥ˆ°(€€€€€€€€‰Ù…±¥‘…Ñ¥½¹}•ÉÉ½ÉÌˆèÍ½ÉÑ•¡•ÉÉ½ÉÌ¤°(€€€€€€€€‰½¹•}±¥•¹Ñ}É•Á½ÉÐˆèQÉÕ”°(€€€€€€€€‰±¥•¹Ñ}‘•±¥Ù•Éå}…±±½Ý•ˆè¹½Ð•ÉÉ½ÉÌ°(€€€ô(()‘•˜…ÑÑ…¡}…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…” (€€€É•½Éè5…ÁÁ¥¹mÍÑÈ°¹åt°(€€€µ…¹¥™•ÍÐè5…ÁÁ¥¹mÍÑÈ°¹åt°(¤€´ø‘¥ÑmÍÑÈ°¹åtè(€€€ÕÁ‘…Ñ•€ô‘••Á½Áä¡‘¥Ð¡É•½É¤¤(€€€¥˜}Ñ•áÐ¡}É•Ù¥•Ý}µ•Ñ…‘…Ñ„¡µ…¹¥™•ÍÐ¤¹•Ð ‰‘•¥Í¥½¸ˆ¤¤¹…Í•™½± ¤€„ô€‰…ÁÁÉ½Ù•ˆè(€€€€€€€ÕÁ‘…Ñ•¹Á½À ‰…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…”ˆ°9½¹”¤(€€€€€€€ÕÁ‘…Ñ•‘l‰±¥•¹Ñ}‘•±¥Ù•Éå}…±±½Ý•‰t€ô…±Í”(€€€€€€€É•ÑÕÉ¸ÕÁ‘…Ñ•(€€€É•ÅÕ¥É•}¹•Ý}É•Á½ÉÑ}…™Ñ•É}•Ù¥‘•¹•}É•ÅÕ•ÍÐ¡ÕÁ‘…Ñ•°µ…¹¥™•ÍÐ¤(€€€‰½Õ¹€ô‰¥¹‘}Á¡…Í”Ñ}…ÁÁÉ½Ù…±}µ…¹¥™•ÍÐ¡ÕÁ‘…Ñ•°µ…¹¥™•ÍÐ¤(€€€ÕÁ‘…Ñ•‘l‰…•ÁÑ•‘}•‘¥Ñ¥½¸‰t€ô‘••Á½Áä¡‰½Õ¹¤(€€€‘•±¥Ù•Éä€ô‰Õ¥±‘}…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…”¡ÕÁ‘…Ñ•°‰½Õ¹¤(€€€ÕÁ‘…Ñ•‘l‰…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…”‰t€ô‘•±¥Ù•Éä(€€€ÕÁ‘…Ñ•‘l‰±¥•¹Ñ}‘•±¥Ù•Éå}…±±½Ý•‰t€ôQÉÕ”(€€€½¹Ñ•áÐ€ô‘••Á½Áä¡‘¥Ð¡ÕÁ‘…Ñ•¹•Ð ‰É•Ù¥•Ý}½¹Ñ•áÐˆ¤½Èíô¤¤(€€€½¹Ñ•áÐ¹ÕÁ‘…Ñ” (€€€€€€€ì(€€€€€€€€€€€€‰Á¡…Í”Ñ}…ÁÁÉ½Ù…±}É••¥ÁÑ}Í¡„ÈÔØˆè‘•±¥Ù•Éål‰Á¡…Í”Ñ}…ÁÁÉ½Ù…±}É••¥ÁÑ}Í¡„ÈÔØ‰t°(€€€€€€€€€€€€‰‘•±¥Ù•Éå}…ÕÑ¡½É¥é…Ñ¥½¹}•ÉÑ¥™¥…Ñ•}Í¡„ÈÔØˆè‘•±¥Ù•Éål‰•ÉÑ¥™¥…Ñ”‰ul(€€€€€€€€€€€€€€€€‰‘•±¥Ù•Éå}…ÕÑ¡½É¥é…Ñ¥½¹}•ÉÑ¥™¥…Ñ•}Í¡„ÈÔØˆ(€€€€€€€€€€€t°(€€€€€€€€€€€€‰±¥•¹Ñ}¥‘•¹Ñ¥Ñäˆè‘•±¥Ù•Éål‰•ÉÑ¥™¥…Ñ”‰ul‰±¥•¹Ñ}¥‘•¹Ñ¥Ñä‰t°(€€€€€€€€€€€€‰ÁÉ½©•Ñ}¥‘•¹Ñ¥Ñäˆè‘•±¥Ù•Éål‰•ÉÑ¥™¥…Ñ”‰ul‰ÁÉ½©•Ñ}¥‘•¹Ñ¥Ñä‰t°(€€€€€€€€€€€€‰Á…­…•}±…ÍÍ¥™¥…Ñ¥½¸ˆè1%9Q}%91}1MM%%Q%=8°(€€€€€€€€€€€€‰½¹•}±¥•¹Ñ}É•Á½ÉÐˆèQÉÕ”°(€€€€€€€€€€€€‰±¥•¹Ñ}Á‘™}½Õ¹Ðˆè€Ä°(€€€€€€€€€€€€‰¡Õµ…¹}É•Ù¥•Ý}É•ÅÕ¥É•ˆèQÉÕ”°(€€€€€€€€€€€€‰±¥•¹Ñ}‘•±¥Ù•Éå}…±±½Ý•ˆèQÉÕ”°(€€€€€€€ô(€€€€¤(€€€ÕÁ‘…Ñ•‘l‰É•Ù¥•Ý}½¹Ñ•áÐ‰t€ô½¹Ñ•áÐ(€€€Ù…±¥‘…Ñ¥½¸€ôÙ…±¥‘…Ñ•}…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…”¡ÕÁ‘…Ñ•°‘•±¥Ù•Éä¤(€€€¥˜Ù…±¥‘…Ñ¥½¹l‰ÍÑ…ÑÕÌ‰t€„ô€‰Ù…±¥ˆè(€€€€€€€É…¥Í”Y…±Õ•ÉÉ½È (€€€€€€€€€€€€‰¥¹Ù…±¥‘}Á¡…Í”Ñ}…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…”èˆ(€€€€€€€€€€€€¬€ˆ°ˆ¹©½¥¸¡Ù…±¥‘…Ñ¥½¹l‰Ù…±¥‘…Ñ¥½¹}•ÉÉ½ÉÌ‰t¤(€€€€€€€€¤(€€€™É½´¹¥¼¹½µÁÉ•¡•¹Í¥Ù•}ÉÕ¹}É•½É¥µÁ½ÉÐ}É•½É‘}¡…Í ((€€€ÕÁ‘…Ñ•‘l‰¥¹Ñ•É¥Ñå}Í¡„ÈÔØ‰t€ô}É•½É‘}¡…Í ¡ÕÁ‘…Ñ•¤(€€€É•ÑÕÉ¸ÕÁ‘…Ñ•(()}}…±±}|€ôl(€€€€‰YIM%=8ˆ°(€€€€‰…ÑÑ…¡}…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…”ˆ°(€€€€‰‰¥¹‘}Á¡…Í”Ñ}…ÁÁÉ½Ù…±}µ…¹¥™•ÍÐˆ°(€€€€‰‰Õ¥±‘}…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…”ˆ°(€€€€‰Ù…±¥‘…Ñ•}…ÁÁÉ½Ù•‘}‘•±¥Ù•Éå}Á…­…”ˆ°)t