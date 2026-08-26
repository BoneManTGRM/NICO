from __future__ import annotations


def test_scanner_truth_manifest_attachment_rehashes_exact_final_canonical_json() -> None:
    from nico import comprehensive_report_package as report_module
    from nico.comprehensive_pre_render_scanner_truth_v65 import _attach_manifest

    canonical = {
        "service_id": "comprehensive",
        "identity": {
            "run_id": "comprun_hash_release_fixture",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger-hash-release-fixture",
            "customer_id": "customer-scope",
            "project_id": "project-scope",
        },
        "assessment": {
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
        },
        "stage_summaries": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    initial_sha = report_module._canonical_hash(canonical)
    result = {
        "canonical_truth_sha256": initial_sha,
        "report_package": {
            "json": canonical,
            "canonical_truth_sha256": initial_sha,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "assessment": {
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    manifest = {
        "version": "nico.comprehensive_pre_render_scanner_truth.v65",
        "status": "applied",
        "pre_flatten_truth_enforced": True,
        "requested": ["bandit"],
        "completed": ["bandit"],
        "incomplete": [],
        "coverage": 100,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    attached = _attach_manifest(result, manifest)
    final_canonical = attached["report_package"]["json"]
    final_sha = report_module._canonical_hash(final_canonical)

    assert final_canonical["pre_render_scanner_truth"] == manifest
    assert final_sha != initial_sha
    assert attached["canonical_truth_sha256"] == final_sha
    assert attached["report_package"]["canonical_truth_sha256"] == final_sha
    assert attached["human_review_required"] is True
    assert attached["client_delivery_allowed"] is False
