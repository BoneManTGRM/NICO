"""Synthetic characterization of v4 checks; expected outcomes captured before extraction."""
from __future__ import annotations

import base64
import io
import json
import warnings
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

import nico.comprehensive_approved_delivery_v4 as delivery_v4
from test_phase4_approved_delivery_v4 import (
    _decision_and_manifest,
    _fully_rehash_archive,
)


@pytest.fixture(scope="module")
def approved_record():
    record, manifest = _decision_and_manifest()
    return delivery_v4.attach_approved_delivery_package(record, manifest)


def characterization_cases():
    cases = ["valid", "non_mapping", "missing_manifest", "missing_receipt",
             "missing_authorization", "invalid_base64", "invalid_zip", "duplicate_path",
             "missing_archive_manifest", "invalid_manifest_json", "non_mapping_manifest",
             "invalid_manifest_utf8", "missing_archive_receipt", "missing_approval_record",
             "missing_archive_authorization", "no_pdf", "wrong_pdf_path",
             "multiple_pdf", "malformed_archive_count", "malformed_package_count",
             "malformed_certificate_count", "missing_certificate", "multiple_errors"]
    for key in ("product_name", "package_classification", "one_client_report",
                "human_review_required", "client_delivery_allowed", "final_human_approval_status",
                "client_delivery_authorization_status", "authorized_edition_created",
                "approved_source_pdf_sha256", "delivery_authorization_certificate_page_prepended",
                "client_facing_status", "approval_certificate_separate_json"):
        cases.append("package:" + key)
    for key in ("repository", "run_id", "report_language", "delivery_status",
                "client_facing_status", "human_review_required", "client_delivery_allowed",
                "one_client_report", "artifact_count", "phase4_approval_receipt_path",
                "phase4_approval_receipt_sha256", "delivery_authorization_path",
                "delivery_authorization_sha256", "artifacts"):
        cases.append("manifest:" + key)
    for key in ("reviewer_identity", "one_client_report", "human_review_required",
                "client_delivery_allowed", "authorized_edition_created",
                "delivery_authorization_certificate_page_prepended", "approval_certificate_page_appended",
                "approved_report_pdf_preserved_exactly", "approval_certificate_separate_json",
                "report_analysis_regenerated_during_delivery_packaging", "delivery_package_sha256"):
        cases.append("certificate:" + key)
    return cases


def mutated_inputs(approved_record, case):
    record = deepcopy(approved_record)
    package = record["approved_delivery_package"]
    if case == "non_mapping":
        return record, None
    if case == "missing_manifest":
        record.pop("accepted_edition")
    elif case == "missing_receipt":
        package.pop("phase4_approval_receipt")
    elif case == "missing_authorization":
        record.pop("delivery_authorization")
    elif case == "invalid_base64":
        package["zip_base64"] = "!"
    elif case == "invalid_zip":
        package["zip_base64"] = base64.b64encode(b"not a zip").decode()
    elif case == "malformed_package_count":
        package["client_pdf_count"] = "bad-count"
    elif case == "malformed_certificate_count":
        package["certificate"]["client_pdf_count"] = "bad-count"
    elif case == "missing_certificate":
        package.pop("certificate")
    elif case == "multiple_errors":
        package.update(product_name="wrong", human_review_required=False,
                       client_delivery_allowed=False, zip_base64="!")
    elif case.startswith("package:"):
        package.pop(case.split(":", 1)[1])
    elif case.startswith("certificate:"):
        package["certificate"].pop(case.split(":", 1)[1])
    elif case.startswith("manifest:") or case == "malformed_archive_count":
        key = case.split(":", 1)[1] if ":" in case else "client_pdf_count"
        package = _fully_rehash_archive(package, manifest_changes={key: "bad-count" if case == "malformed_archive_count" else ([] if key == "artifacts" else None)})
    elif case != "valid":
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(package["zip_base64"]))) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        manifest_path = "11_evidence_manifest.json"
        removals = {"missing_archive_manifest": manifest_path,
                    "missing_archive_receipt": "12_phase4_approval_receipt.json",
                    "missing_approval_record": "15_approval_record.json",
                    "missing_archive_authorization": "16_delivery_authorization.json",
                    "no_pdf": "01_nico_comprehensive_report.pdf"}
        if case in removals:
            entries.pop(removals[case])
        elif case in ("invalid_manifest_json", "non_mapping_manifest", "invalid_manifest_utf8"):
            entries[manifest_path] = {"invalid_manifest_json": b"{", "non_mapping_manifest": b"[]", "invalid_manifest_utf8": b"\xff"}[case]
        elif case == "wrong_pdf_path":
            entries["wrong.pdf"] = entries.pop("01_nico_comprehensive_report.pdf")
        elif case == "multiple_pdf":
            entries["second.pdf"] = b"synthetic"
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, content in entries.items():
                    archive.writestr(name, content)
                if case == "duplicate_path":
                    archive.writestr("15_approval_record.json", entries["15_approval_record.json"])
        package["zip_base64"] = base64.b64encode(buffer.getvalue()).decode()
    return record, package


def outcome(record, package):
    try:
        return {"result": delivery_v4.validate_approved_delivery_package(record, package)}
    except Exception as exc:
        return {"exception": type(exc).__name__, "message": str(exc)}


@pytest.mark.parametrize("case", characterization_cases())
def test_v4_exact_characterized_outcomes(approved_record, monkeypatch, case):
    # Isolate inherited v3 output so these snapshots pin v4's full result and errors.
    monkeypatch.setattr(delivery_v4, "validate_v3", lambda *_: {"status": "valid", "validation_errors": [], "inherited": "preserved"})
    record, package = mutated_inputs(approved_record, case)
    before = deepcopy((record, package))
    expected = json.loads(Path(__file__).with_name("phase4_validator_outcomes.json").read_text())
    assert outcome(record, package) == expected[case]
    assert (record, package) == before


def test_genuine_valid_result_preserves_full_shape(approved_record):
    package = approved_record["approved_delivery_package"]
    assert delivery_v4.validate_approved_delivery_package(approved_record, package) == {
        "status": "valid", "validation_errors": [], "zip_sha256": package["zip_sha256"],
        "zip_size_bytes": package["zip_size_bytes"], "artifact_schema": delivery_v4.VERSION,
        "one_client_report": True, "client_delivery_allowed": True,
    }


def test_inherited_errors_are_sorted_and_deduplicated(monkeypatch):
    monkeypatch.setattr(delivery_v4, "validate_v3", lambda *_: {"validation_errors": ["z", "a", "z"], "marker": 42})
    assert delivery_v4.validate_approved_delivery_package({}, None) == {
        "validation_errors": ["a", "phase4_delivery_package_must_be_mapping", "z"],
        "marker": 42, "status": "invalid", "client_delivery_allowed": False,
    }


def test_inherited_value_error_is_bounded_but_other_exceptions_propagate(monkeypatch):
    def fail(*_):
        raise ValueError("synthetic_failure:private detail")
    monkeypatch.setattr(delivery_v4, "validate_v3", fail)
    assert delivery_v4.validate_approved_delivery_package({}, None) == {
        "status": "invalid", "client_delivery_allowed": False,
        "validation_errors": ["phase4_delivery_package_must_be_mapping", "phase4_inherited_validation_failed:synthetic_failure"],
    }
    def fail_type(*_):
        raise TypeError("synthetic failure")
    monkeypatch.setattr(delivery_v4, "validate_v3", fail_type)
    with pytest.raises(TypeError, match="synthetic failure"):
        delivery_v4.validate_approved_delivery_package({}, None)
