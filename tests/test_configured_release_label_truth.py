from nico.comprehensive_release_provenance_v1 import comprehensive_release_provenance, _provenance_lines


def test_configured_frontend_label_is_not_an_established_runtime_identity(monkeypatch):
    monkeypatch.setenv("NICO_FRONTEND_BUILD_COMMIT_SHA", "a" * 40)
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    provenance = comprehensive_release_provenance()
    assert provenance["frontend_build_commit"] == "a" * 40
    assert provenance["frontend_identity_established"] is False
    assert dict(_provenance_lines(provenance))["Configured frontend source commit"] == "a" * 40


def test_mismatching_endpoint_claim_is_retained_without_becoming_verified():
    provenance = {"frontend_build_commit": "a" * 40, "frontend_identity_source": "configured_release_label",
                  "frontend_runtime_observation": {"status": "mismatch", "release_sha": "b" * 40,
                     "deployment_id": "dpl_fixture", "observed_at": "2026-09-15T00:00:00Z"}}
    rows = dict(_provenance_lines(provenance))
    assert rows["Retained frontend endpoint claim"] == "b" * 40
    assert rows["Frontend observation status"] == "mismatch"
    assert provenance["frontend_runtime_observation"]["status"] == "mismatch"
