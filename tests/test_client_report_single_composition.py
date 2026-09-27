"""Exercise the real compact finalizer without a disposable detailed PDF pass."""
from __future__ import annotations

import base64
from copy import deepcopy
import io

from pypdf import PdfReader
import pytest

from nico import client_report_completion_v1 as legacy
from nico import client_report_completion_v2 as compact
from tests.test_client_report_completion_v2 import _package


def _owned_package(count: int = 1, *, spanish: bool = False) -> dict:
    package = _package()
    canonical = package["json"]
    finding = deepcopy(canonical["canonical_findings"][0])
    hotspot = deepcopy(canonical["complexity_evidence"]["hotspots"][0])
    canonical["canonical_findings"] = []
    canonical["complexity_evidence"]["hotspots"] = []
    for index in range(count):
        path = f"apps/web/app/owned/module_{index:04d}.tsx"
        name = f"OwnedFunction{index:04d}"
        canonical["canonical_findings"].append(finding | {
            "finding_id": f"OWNED-{index:04d}",
            "title": f"{name} has concentrated branching and elevated change risk",
            "location": path + ":177",
        })
        canonical["complexity_evidence"]["hotspots"].append(hotspot | {
            "path": path, "name": name,
            "source_excerpt": f"export function {name}() {{ return null; }}",
        })
    canonical["identity"]["report_language"] = "es-MX" if spanish else "en"
    return package


def _text(result: dict) -> str:
    reader = PdfReader(io.BytesIO(base64.b64decode(result["pdf_base64"])))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


@pytest.mark.parametrize("spanish", [False, True])
def test_compact_finalizer_never_renders_disposable_detailed_register(monkeypatch, spanish):
    package = _owned_package(80, spanish=spanish)
    untouched = deepcopy(package)

    def forbidden(*args, **kwargs):
        pytest.fail("compact finalizer rendered a disposable legacy finding PDF")

    monkeypatch.setattr(legacy, "render_finding_register_pdf", forbidden)
    result = compact.finalize_client_report_package(package)
    text = _text(result)
    assert package == untouched
    assert result["finding_population"]["decision_finding_count"] == 80
    assert len(result["json"]["canonical_findings"]) == 80
    for finding in result["client_finding_remediation_register"]["code_findings"]:
        assert legacy._compact(finding["location"]) in legacy._compact(text)
    assert "Exact commit" in text
    assert result["pdf_page_count"] <= 60
    assert result["human_review_required"] is True
    assert result["human_review_completed"] is False
    assert result["client_delivery_allowed"] is False
    assert result["approval_status"] == "pending_human_approval"
    assert result["client_report_completion"]["exact_source_locations_verified_in_pdf"] is True
    assert result["client_report_completion"]["verification_and_exit_criteria_distinct"] is True


def test_legacy_finalizer_keeps_its_full_renderer_and_validation(monkeypatch):
    calls = []
    original = legacy.render_finding_register_pdf

    def tracked(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(legacy, "render_finding_register_pdf", tracked)
    result = legacy.finalize_client_report_package(_owned_package())
    assert calls == [True]
    assert result["client_report_completion"]["finding_register_in_pdf"] is True
    assert result["client_delivery_allowed"] is False


def test_compact_finalizer_still_fails_on_invalid_required_register(monkeypatch):
    monkeypatch.setattr(compact, "render_compact_finding_register_pdf", lambda *a, **k: b"invalid")
    with pytest.raises(ValueError, match="valid register PDF"):
        compact.finalize_client_report_package(_owned_package())


def test_final_validation_rejects_a_missing_not_applicable_analyzer():
    result = compact.finalize_client_report_package(_owned_package())
    canonical = deepcopy(result["json"])
    canonical["not_applicable_scanner_records"] = [{"scanner_name": "OWNED_ABSENT_ANALYZER"}]
    with pytest.raises(ValueError, match="not-applicable analyzer"):
        compact._validate_final_surfaces(
            canonical, result["client_finding_remediation_register"],
            result["markdown"], result["html"], base64.b64decode(result["pdf_base64"]),
        )


def test_bound_package_keeps_existing_reuse_receipt(monkeypatch):
    from nico.comprehensive_rendered_package_reuse_v1 import install_comprehensive_rendered_package_reuse_v1
    install_comprehensive_rendered_package_reuse_v1()
    package = _owned_package()
    package["premium_report_renderer"]["single_pass_renderer"] = True

    def forbidden(*args, **kwargs):
        pytest.fail("completed renderer package entered legacy data preparation")

    monkeypatch.setattr(legacy, "_prepare_completion_text", forbidden, raising=False)
    result = compact.finalize_client_report_package(package)
    assert result["client_report_completion"]["legacy_rerender_skipped"] is True
    assert result["client_delivery_allowed"] is False
