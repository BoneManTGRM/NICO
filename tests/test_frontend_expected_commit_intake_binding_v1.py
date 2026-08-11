from __future__ import annotations

from pathlib import Path


SOURCE = Path("apps/web/app/assessment/assessmentRunRequests.ts").read_text(encoding="utf-8")


def test_browser_intake_binds_exact_sha_from_production_proof_url() -> None:
    assert 'const INTAKE_PATH = "/assessment/comprehensive-intake"' in SOURCE
    assert 'searchParams.get("expected_commit_sha")' in SOURCE
    assert "EXACT_SHA_RE" in SOURCE
    assert "expected_commit_sha: expectedCommitSha" in SOURCE
    assert 'code: "invalid_explicit_commit_sha"' in SOURCE
    assert 'code: "assessment_expected_commit_sha_conflict"' in SOURCE


def test_exact_sha_binding_is_limited_to_post_intake() -> None:
    assert 'path !== INTAKE_PATH || method !== "POST"' in SOURCE
    assert "const boundInit = bindExpectedCommitSha(path, init);" in SOURCE
    assert "headers: browserHeaders(boundInit.headers)" in SOURCE
    assert "signal: controller?.signal || boundInit.signal" in SOURCE
