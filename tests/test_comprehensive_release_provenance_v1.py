from __future__ import annotations

import base64
import sys


def test_release_provenance_is_bound_to_all_report_formats(monkeypatch):
    from nico import comprehensive_report_package as package
    from nico.comprehensive_release_provenance_v1 import (
        install_comprehensive_release_provenance,
    )

    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("NICO_FRONTEND_BUILD_COMMIT_SHA", "b" * 40)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "deployment-test")

    # The installer also binds helpers captured during eager package imports.
    # Restore those globals with the environment so later tests retain their
    # original renderer state instead of inheriting this test's installation.
    for name in (
        "nico.comprehensive_canonical_report_source_v1",
        "nico.v2_premium_report_renderer",
        "nico.comprehensive_spanish_canonical_report_v87",
        "nico.comprehensive_same_run_locale_report_v1",
    ):
        module = sys.modules.get(name)
        if module is None:
            continue
        for attribute in ("_assessment", "_markdown", "_pdf"):
            if hasattr(module, attribute):
                monkeypatch.setattr(module, attribute, getattr(module, attribute))
        flag = "_nico_release_provenance_v1_installed"
        monkeypatch.setattr(module, flag, getattr(module, flag, False), raising=False)

    originals = (package._assessment, package._markdown, package._pdf)
    prior_flag = getattr(package, "_nico_release_provenance_v1_installed", False)
    try:
        setattr(package, "_nico_release_provenance_v1_installed", False)
        installed = install_comprehensive_release_provenance()
        assert installed["canonical_json_bound"] is True
        result = package.build_comprehensive_report_package(
            identity={
                "run_id": "comprun_provenance_test",
                "repository": "owner/repository",
                "commit_sha": "c" * 40,
                "evidence_ledger_id": "ledger_provenance_test",
                "customer_id": "customer",
                "project_id": "project",
                "report_language": "en",
            },
            stage_results={},
        )
        assert result["status"] == "complete"
        report = result["report_package"]
        provenance = report["json"]["assessment"]["nico_release_provenance"]
        assert provenance["backend_build_commit"] == "a" * 40
        assert provenance["frontend_build_commit"] == "b" * 40
        assert provenance["deployment_identity_established"] is True
        assert "NICO Release Provenance" in report["markdown"]
        assert "a" * 40 in report["markdown"]
        assert "NICO Release Provenance" in report["html"]
        assert base64.b64decode(report["pdf_base64"], validate=True).startswith(b"%PDF")
        assert report["pdf_page_count"] >= 2
    finally:
        package._assessment, package._markdown, package._pdf = originals
        setattr(package, "_nico_release_provenance_v1_installed", prior_flag)
