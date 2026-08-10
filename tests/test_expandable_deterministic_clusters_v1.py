import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps/web/app/operations/reviewer-queue/ReviewerQueue.tsx"
CSS = ROOT / "apps/web/app/operations/reviewer-queue/reviewer-queue.module.css"
API_ROUTES = ROOT / "nico/comprehensive_api_routes.py"
STATE = ROOT / "docs/client-ready-report-accuracy-observation.json"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_wp2_implements_only_the_declared_expandable_cluster_scope() -> None:
    state = json.loads(source(STATE))
    component = source(COMPONENT)

    assert state["next_work_package"] == "expandable_deterministic_clusters"
    assert state["next_work_package_state"] == "declared_not_started"
    scope = state["next_work_package_scope"]
    assert scope["consume_existing_exception_queue"] is True
    assert scope["consume_existing_canonical_candidate_register"] is True
    assert scope["expand_deterministic_cluster_summaries"] is True
    assert scope["expand_every_underlying_candidate"] is True
    assert scope["expose_complete_retained_candidate_evidence"] is True
    assert scope["accessible_keyboard_operable_expansion"] is True
    assert scope["candidate_cluster_identity_and_workload_parity_fail_closed"] is True
    assert scope["read_only"] is True
    assert scope["candidate_or_group_disposition_controls"] is False
    assert scope["quality_control_sampling"] is False
    assert scope["reviewer_time_measurement"] is False
    assert 'data-review-queue-contract="exception-first-v1"' in component
    assert 'data-cluster-expansion-contract="expandable-deterministic-clusters-v1"' in component


def test_clusters_and_underlying_candidates_are_keyboard_operable_and_expandable() -> None:
    component = source(COMPONENT)
    css = source(CSS)

    assert "function ClusterCard" in component
    assert "function CandidateReviewCard" in component
    assert "function ExpansionButton" in component
    assert 'type="button"' in component
    assert "aria-expanded={expanded}" in component
    assert "aria-controls={controls}" in component
    assert "unit.candidates.map" in component
    assert "representativeSummary" in component
    assert "expandedClusters.has(unit.id)" in component
    assert "expandedCandidates.has(id)" in component
    assert "Expand ${unit.candidates.length} underlying candidates" in component
    assert ".expandButton:focus-visible" in css


def test_complete_canonical_candidate_record_is_subordinate_to_cluster_summary() -> None:
    component = source(COMPONENT)

    assert "function CompleteCandidateRecord" in component
    assert "Object.entries(candidate).sort" in component
    assert 'data-candidate-record-projection="complete-canonical-record"' in component
    assert "Every retained evidence, lineage, clustering, and proposal-only technical-triage field is shown" in component
    assert "Cluster summaries never replace candidate-level evidence" in component
    assert "The cluster summary is routing context only" in component
    assert "Secret values remain redacted by the canonical evidence projection" in component
    assert "technical_triage_rationale" in component
    assert "technical_triage_proof_gaps" in component
    assert "technical_triage_recommended_next_step" in component


def test_candidate_cluster_identity_and_workload_parity_fail_closed() -> None:
    component = source(COMPONENT)

    required_contracts = (
        "The canonical register is not complete.",
        "candidate ID.",
        "Candidate identities are not unique.",
        "candidate-count parity proof",
        "retained raw candidate count",
        "stable identity for every retained raw candidate",
        "mutually-exclusive disposition proof",
        "complete retained candidate payload coverage",
        "redaction-preserving source fingerprints",
        "preserve source evidence-quality totals",
        "source and rendered projection digests",
        "deterministic cluster ID",
        "valid proposal-only technical-triage verdict",
        "valid reviewer-routing class",
        "complete proposal-only technical-triage context",
        "impermissible carried-forward human approval",
        "misrepresents automated routing as a human decision",
        "cluster size that does not match",
        "deterministic cluster membership that does not match",
        "one valid representative candidate",
        "one deterministic cluster reason",
        "one deterministic review work-unit identity",
        "conflicting technical-triage verdicts",
        "mixes grouped and individual review routing",
        "The queue does not preserve every canonical candidate exactly once.",
        "Displayed work units do not reconcile",
        "Grouped-review candidates do not reconcile",
        "Deterministic cluster totals do not reconcile",
    )
    for contract in required_contracts:
        assert contract in component

    assert "const integrityFailed = Boolean(model?.integrityErrors.length)" in component
    assert "Candidate and cluster evidence will not be displayed until exact-run parity is restored." in component
    assert "integrityErrors.slice(0, 100)" in component
    assert "{integrityFailed ?" in component
    assert "model.individualUnits.map" in component
    assert "model.groupedUnits.map" in component


def test_exact_run_security_and_human_boundaries_remain_read_only() -> None:
    component = source(COMPONENT)
    api_routes = source(API_ROUTES)

    assert '"X-NICO-Admin-Token"' in component
    assert 'type="password"' in component
    assert 'setAdminToken("")' in component
    assert "localStorage" not in component
    assert "sessionStorage" not in component
    assert 'method: "POST"' not in component
    assert 'data-human-disposition-controls="absent"' in component
    assert 'data-client-delivery-authorization="absent"' in component
    assert "No candidate disposition, reviewer identity, risk acceptance, approval, score change" in component
    assert "human_review_required" in component
    assert "client_delivery_allowed" in component

    assert '@app.get("/assessment/comprehensive-run/{run_id}/review-queue")' in api_routes
    assert "_authorize_review(x_nico_admin_token)" in api_routes
    assert "canonical_scanner_finding_register" in api_routes
    assert '"read_only": True' in api_routes
    assert '"client_delivery_allowed": False' in api_routes
