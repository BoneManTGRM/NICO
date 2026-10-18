"""Dormant complete-family finalization. No installer, route, storage or approval.

Prepared localized components must already carry draft-status presentation. Core navigation and
page labels are final before collective semantic validation and file-family freeze.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

from nico import ordinary_review_bundle_v2 as core
from nico import ordinary_report_files_v2 as transport
from nico.client_pdf_compose_v2 import review_bundle_sections
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256

SCHEMA = "nico.ordinary-review-bundle.freeze.v2"


def _snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = core._json(value)
    if len(raw) > transport.MAX_TEXT_BYTES:
        raise ValueError("family_freeze_canonical_size")
    result = transport._json_object(raw)
    if not isinstance(result, dict):
        raise ValueError("family_freeze_canonical_object")
    return result


def _inventory(sections: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    return [{"section_id": name, "sha256": core._sha(data), "size_bytes": len(data),
             "page_count": len(reader.pages),
             "page_digests": [core._page_digest(page) for page in reader.pages]}
            for name, data in sections for reader in [core._reader(data)]]


def finalize_spanish_review_family(
    *, source_canonical: Mapping[str, Any], expected_source_truth_sha256: str,
    localized_canonical: Mapping[str, Any], register: Mapping[str, Any],
    exports: Mapping[str, str], components: Mapping[str, bytes | None],
) -> dict[str, Any]:
    """Return one complete review-only family or raise, without publishing any part."""
    source, canonical, register = map(_snapshot, (source_canonical, localized_canonical, register))
    source_digest = canonical_sha256(source)
    if source_digest != expected_source_truth_sha256:
        raise ValueError("family_freeze_source_truth")
    source_identity, local_identity = source.get("identity"), canonical.get("identity")
    if not isinstance(source_identity, Mapping) or not isinstance(local_identity, Mapping):
        raise ValueError("family_freeze_identity")
    if local_identity.get("report_language") != "es-MX":
        raise ValueError("family_freeze_dormant_spanish_only")
    if any(source_identity.get(key) != local_identity.get(key) for key in ("run_id", "repository", "commit_sha")):
        raise ValueError("family_freeze_source_identity")
    local_digest = canonical_sha256(canonical)
    identity = core._identity({**{key: local_identity.get(key) for key in
        ("run_id", "repository", "commit_sha", "report_language")},
        "canonical_truth_sha256": local_digest})
    exports = dict(exports)
    if set(exports) != set(transport.EXPORT_NAMES):
        raise ValueError("report_files_export_population")
    if any(type(value) is not str for value in exports.values()):
        raise ValueError("report_files_export_invalid")
    if sum(len(value.encode("utf-8")) for value in exports.values()) > transport.MAX_TEXT_BYTES:
        raise ValueError("report_files_text_limit")
    canonical_bytes = exports["canonical_json"].encode("utf-8")
    if transport._json_object(canonical_bytes) != canonical:
        raise ValueError("family_freeze_locale_canonical_bytes")
    # This rejects unauthorized lifecycle states; it never sets them to pass.
    transport._canonical_identity(canonical_bytes, identity)
    components = dict(components)
    required = {"base_pdf", "register_pdf", "gate_pdf", "review_pdf", "ci_boundary_pdf"}
    if not required <= set(components) or set(components) - required - {"human_evidence_pdf"}:
        raise ValueError("bundle_required_component_missing")
    if any(type(components[key]) is not bytes for key in required):
        raise ValueError("bundle_required_component_missing")
    if components.get("human_evidence_pdf") is not None and type(components["human_evidence_pdf"]) is not bytes:
        raise ValueError("bundle_pdf_input")
    if sum(len(value) for value in components.values() if value is not None) > core.MAX_BYTES:
        raise ValueError("bundle_byte_limit")
    # Select once, then bind the exact selected bytes before construction.
    # Reject unsafe prose during semantic validation; never sanitize or reorder
    # already selected source pages inside the freeze boundary.
    sections = review_bundle_sections(**components)
    expected_inventory = _inventory(sections)
    bundle = core.build_review_bundle(identity, sections)
    if bundle["manifest"]["source_sections"] != expected_inventory:
        raise ValueError("family_freeze_selected_page_inventory")
    core.validate_review_bundle(bundle, expected_identity=identity,
                                expected_manifest_sha256=bundle["manifest_sha256"])
    pdfs = tuple(base64.b64decode(item["pdf_base64"], validate=True) for item in bundle["files"])
    from nico.client_report_completion_v2 import _validate_final_volume_surfaces, _REVIEW_SECTION_TITLES_ES
    from nico.report_pdf_text import extract_pdf_page_texts
    from nico import client_report_completion_v1 as legacy
    collective_text = "\n".join(text for pdf in pdfs for text in extract_pdf_page_texts(pdf))
    if any(title not in collective_text for title in _REVIEW_SECTION_TITLES_ES):
        raise ValueError("family_freeze_pdf_review_sections_missing")
    compact_text = legacy._compact(collective_text)
    for item in register.get("code_findings") or []:
        if isinstance(item, Mapping) and item.get("location"):
            if legacy._compact(str(item["location"])) not in compact_text:
                raise ValueError("family_freeze_pdf_source_location_missing")
    validation = _validate_final_volume_surfaces(canonical, register,
        exports["markdown_report"], exports["html_report"], pdfs)
    # No PDF mutation or navigation work is permitted after this point.
    family = transport.build_report_files(bundle, exports, expected_identity=identity,
        expected_bundle_manifest_sha256=bundle["manifest_sha256"])
    receipt = {"artifact_schema": SCHEMA, "source_truth_sha256": source_digest,
               "locale_canonical_truth_sha256": local_digest,
               "locale_canonical_json_sha256": core._sha(canonical_bytes),
               "identity": identity, "selected_sections": expected_inventory,
               "family_manifest_sha256": family["manifest_sha256"],
               "semantic_validation": validation}
    frozen = {"artifact_schema": SCHEMA, "receipt": receipt,
              "receipt_sha256": core._sha(core._json(receipt)), "report_bundle": family}
    validate_frozen_spanish_family(frozen, expected_source_truth_sha256=source_digest,
        expected_identity=identity, expected_receipt_sha256=frozen["receipt_sha256"])
    return frozen


def validate_frozen_spanish_family(frozen: Mapping[str, Any], *, expected_source_truth_sha256: str,
                                  expected_identity: Mapping[str, str], expected_receipt_sha256: str) -> None:
    if set(frozen) != {"artifact_schema", "receipt", "receipt_sha256", "report_bundle"} or frozen["artifact_schema"] != SCHEMA:
        raise ValueError("family_freeze_schema")
    receipt = frozen["receipt"]
    if frozen["receipt_sha256"] != expected_receipt_sha256 or core._sha(core._json(receipt)) != expected_receipt_sha256:
        raise ValueError("family_freeze_receipt_digest")
    if (receipt["artifact_schema"] != SCHEMA or receipt["source_truth_sha256"] != expected_source_truth_sha256
            or receipt["identity"] != dict(expected_identity)
            or receipt["locale_canonical_truth_sha256"] != expected_identity["canonical_truth_sha256"]):
        raise ValueError("family_freeze_identity")
    members = transport._validated_members(frozen["report_bundle"], expected_identity,
                                           receipt["family_manifest_sha256"])
    if core._sha(members["canonical.json"]) != receipt["locale_canonical_json_sha256"]:
        raise ValueError("family_freeze_locale_canonical_bytes")
    manifest = transport._json_object(members["bundle-manifest.json"])
    if manifest["source_sections"] != receipt["selected_sections"]:
        raise ValueError("family_freeze_selected_page_inventory")
