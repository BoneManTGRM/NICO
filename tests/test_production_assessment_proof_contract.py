from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-assessment-proof.yml"
RUNNER = ROOT / "scripts" / "run_production_assessment_browser_proof.mjs"


def test_production_proof_is_one_shot_serial_and_exact_release_bound() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Production Assessment Proof" in source
    assert "push:" in source
    assert "branches: [main]" in source
    assert "workflow_dispatch:" in source
    assert "group: production-assessment-proof" in source
    assert "cancel-in-progress: false" in source
    assert "EXPECTED_COMMIT: ${{ github.sha }}" in source
    assert "Check out exact proof commit" in source
    assert "ref: ${{ github.sha }}" in source
    assert "timeout-minutes: 70" in source


def test_production_proof_is_explicitly_authorized_and_has_no_operator_secret() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    assert "AUTHORIZED_REPOSITORY: BoneManTGRM/NICO" in workflow
    assert "Owner-authorized defensive production assessment" in workflow
    assert 'AUTHORIZED_REPOSITORY === "BoneManTGRM/NICO"' in runner
    assert 'AUTHORIZATION_SCOPE.toLowerCase().includes("owner-authorized")' in runner
    assert "NICO_ADMIN_TOKEN" not in workflow
    assert "NICO_ADMIN_TOKEN" not in runner
    assert "secrets." not in workflow


def test_browser_proof_starts_each_tier_once_and_preserves_exact_run_identity() -> None:
    source = RUNNER.read_text(encoding="utf-8")

    for route in ("/assessment/github", "/assessment/mid-run", "/assessment/full-run"):
        assert route in source
    assert 'const TIERS = ["express", "mid", "full"]' in source
    assert "startCounts[tier] += 1" in source
    assert "startCount === 1" in source
    assert "did not preserve an exact run ID" in source
    assert "did not preserve an exact repository snapshot commit" in source
    assert "did not preserve a scanner run identity" in source
    assert "did not preserve a report identity" in source
    assert "did not preserve a human-review request identity" in source
    assert "exact-run state was not proven durable in production" in source


def test_browser_proof_stops_at_human_review_and_forbids_delivery_mutation() -> None:
    source = RUNNER.read_text(encoding="utf-8")

    assert "human_review_required === true" in source
    assert "client_ready === false" in source
    assert "crossed the human-review boundary automatically" in source
    for forbidden in (
        "/approval/request",
        "/approved",
        "/delivery/access",
        "/delivery/redeem",
        "/delivery/acknowledg",
    ):
        assert forbidden in source
    assert "forbidden_mutation_requests.length === 0" in source


def test_retained_evidence_is_bounded_and_excludes_raw_reports() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    assert "sanitizeAssessmentPayload" in runner
    assert "has_markdown: Boolean(reports.markdown)" in runner
    assert "has_pdf: Boolean(reports.pdf_base64)" in runner
    assert "markdown: reports.markdown" not in runner
    assert "pdf_base64: reports.pdf_base64" not in runner
    assert "sanitizeProgress" in runner
    assert "item?.evidence" not in runner
    assert "screenshots.push({file, sha256:" in runner
    assert "Upload complete production proof artifact" in workflow
    assert "Publish bounded evidence branch" in workflow
    assert "docs/evidence/production-assessment-proof/${GITHUB_SHA}" in workflow


def test_workflow_publishes_verifiable_status_and_fails_closed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "statuses: write" in source
    assert "contents: write" in source
    assert "context=production-assessment-proof" in source
    assert "state=success" in source
    assert "state=failure" in source
    assert "bounded evidence was retained" in source
    assert "Fail closed when proof did not pass" in source
    assert "test '${{ steps.proof.outputs.exit_code }}' = '0'" in source
