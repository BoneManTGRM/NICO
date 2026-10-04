from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import comprehensive_authoritative_scanner_truth_v62 as truth
from nico import comprehensive_commercial_ship_projection_v3 as commercial

SHA = "a" * 40
TOOLS = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep",
         "eslint", "typescript", "gitleaks", "trufflehog"]


def _record(name, completed=True):
    return {
        "scanner_name": name, "commit_sha": SHA,
        "status": "completed" if completed else "unavailable",
        "completed": completed, "verified": completed,
        "verified_for_this_report": completed, "exact_commit_match": True,
        "artifact_hash": hashlib.sha256(name.encode()).hexdigest() if completed else "",
        "failure_reason": "" if completed else "Project execution is not authorized",
        "findings": [],
    }


def _canonical(paths, names=TOOLS):
    return {
        "identity": {"run_id": "comprun_coverage_diagnostic", "commit_sha": SHA},
        "repository_evidence": {"file_evidence": {"sampled_paths": paths}},
        "requested_scanner_records": [_record(name) for name in names],
        "assessment": {"technical_score": 90},
        # Stale presentation is deliberately not execution authority.
        "client_readiness_contract": {"coverage_numerator": 99, "coverage_denominator": 99},
        "bulk_presentation": {"diagnostic_large_surface": ["Observed retained evidence"] * 3000},
    }


def _status(canonical, claim, language):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(40, 750, claim)
    pdf.drawString(40, 730, "Table of Contents" if language == "en" else "Tabla de contenido")
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS
    pdf.setFont("Helvetica", 8)
    for index, section in enumerate(CANONICAL_TOC_SECTIONS):
        pdf.drawString(40, 712 - index * 15, section["title_en" if language == "en" else "title_es"])
    pdf.save()
    return {
        "human_review_required": True, "human_review_completed": False,
        "approval_status": "pending_human_approval", "client_delivery_allowed": False,
        "reports": {"json": canonical, "pdf_base64": base64.b64encode(buffer.getvalue()).decode(),
                    "markdown": claim, "html": f"<p>{claim}</p>"},
    }


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_source_gate_checks_current_counts_without_copying_full_presentation(monkeypatch, language):
    canonical = _canonical(["src/main.py"], ["bandit"])
    claim = ("1 of 1 applicable scanner executions completed" if language == "en"
             else "1 de 1 ejecuciones de analizadores aplicables completadas")
    status = _status(canonical, claim, language)
    original = deepcopy(status)
    full_surface_copies = []
    real_copy = truth.deepcopy

    def observed_copy(value, *args, **kwargs):
        if isinstance(value, dict) and "bulk_presentation" in value:
            full_surface_copies.append(True)
        return real_copy(value, *args, **kwargs)

    monkeypatch.setattr(truth, "deepcopy", observed_copy)
    assert commercial._source_pdf_requires_integrity_reprojection(status, language) is False
    # Exact-run scanner validation must not clone unrelated retained report presentation.
    assert not full_surface_copies
    assert status == original

    canonical["live_scanner_evidence"] = {"tools_requested": ["bandit"], "failed_tools": ["bandit"]}
    assert commercial._source_pdf_requires_integrity_reprojection(status, language) is True
    # Current lifecycle authority is read every time, independently of identical PDF bytes.
    status.update(human_review_completed=True, approval_status="approved", client_delivery_allowed=True)
    assert commercial._source_pdf_requires_integrity_reprojection(status, language) is False


@pytest.mark.parametrize("paths,names", [
    (["src/main.py", "requirements.txt"], TOOLS),
    (["package.json", "package-lock.json", "src/main.ts", "tsconfig.json"], TOOLS),
    (["src/main.cpp", "include/api.hpp"], ["cppcheck", *TOOLS]),
    (["src/main.cpp", "tests/fixture.ts", "src/main.py", "package.json"], ["cppcheck", *TOOLS]),
    ([], TOOLS), ([], []),
])
@pytest.mark.parametrize("condition", ["complete", "missing", "unavailable", "failed", "timed_out"])
def test_readonly_coverage_matches_full_authoritative_projection(paths, names, condition):
    canonical = _canonical(paths, names)
    if names and condition == "missing":
        canonical["requested_scanner_records"].pop()
        canonical["live_scanner_evidence"] = {"tools_requested": names}
    elif names and condition == "unavailable":
        canonical["requested_scanner_records"][-1] = _record(names[-1], False)
    elif names and condition in {"failed", "timed_out"}:
        canonical["live_scanner_evidence"] = {"tools_requested": names, f"{condition}_tools": [names[-1]]}
    original = deepcopy(canonical)
    contract = truth.reconcile_authoritative_scanner_truth(canonical)["client_readiness_contract"]
    expected = (contract["coverage_numerator"], contract["coverage_denominator"])
    assert truth.authoritative_scanner_execution_coverage(canonical) == expected
    assert canonical == original


@pytest.mark.parametrize("paths", [[], ["main.ts"], ["translations/main.ts"]])
def test_coverage_preserves_source_bound_inventory_and_qt_exclusions(tmp_path, paths):
    from nico.node_scanner_applicability_v1 import inspect_node_inputs

    (tmp_path / "translations").mkdir()
    (tmp_path / "translations/main.ts").write_text(
        '<?xml version="1.0"?><TS version="2.1" language="es_MX"><context/></TS>'
    )
    inventory = inspect_node_inputs(tmp_path, SHA)
    canonical = _canonical(paths, ["typescript"])
    canonical["requested_scanner_records"][0].update(
        status="not_applicable", completed=False, verified=False,
        execution_observed_for_this_report=False, applicability_evidence=inventory,
    )
    original = deepcopy(canonical)
    contract = truth.reconcile_authoritative_scanner_truth(canonical)["client_readiness_contract"]
    assert truth.authoritative_scanner_execution_coverage(canonical) == (
        contract["coverage_numerator"], contract["coverage_denominator"])
    assert canonical == original


def test_verified_native_targets_and_duplicate_scanner_aliases_keep_the_same_population():
    canonical = _canonical([], ["eslint", "eslint", "typescript"])
    for record in canonical["requested_scanner_records"]:
        if record["scanner_name"] == "eslint":
            record["execution_provenance"] = {
                "coverage": {"status": "reported_native_targets", "reported_target_count": 2}
            }
    canonical["scanner_execution_records"] = [_record("bandit", False)]
    canonical["assessment"]["requested_scanner_records"] = [_record("cppcheck", False)]
    contract = truth.reconcile_authoritative_scanner_truth(canonical)["client_readiness_contract"]
    assert truth.authoritative_scanner_execution_coverage(canonical) == (
        contract["coverage_numerator"], contract["coverage_denominator"])
