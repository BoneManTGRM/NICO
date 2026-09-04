from __future__ import annotations

import base64


def test_release_provenance_is_bound_to_all_report_formats(monkeypatch):
    from nico import comprehensive_report_package as package
    from nico.comprehensive_release_provenance_v1 import (
        install_comprehensive_release_provenance,
    )

    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("NICO_FRONTEND_BUILD_COMMIT_SHA", "b" * 40)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "deployment-test")

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
