import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps/web/app/operations/reviewer-queue/ReviewerQueue.tsx"
STYLES = ROOT / "apps/web/app/operations/reviewer-queue/reviewer-queue.module.css"
API_ROUTES = ROOT / "nico/comprehensive_api_routes.py"
STATUS = ROOT / "docs/NICO_COMPLETION_PROGRAM_STATUS.md"
STATE = ROOT / "docs/client-ready-report-accuracy-observation.json"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_authoritative_state_declares_expandable_cluster_package_without_preclaiming_completion() -> None:
    status = source(STATUS)
    state = json.loads(source(STATE))

    assert state["program_phase"] == 2
    assert state["work_package"] == "exception_first_reviewer_interface"
    assert state["dependency_state"] == "completed"
    assert state["state"] == "post_merge_verified"
    assert state["next_work_package"] == "expandable_deterministic_clusters"
    assert state["next_work_package_state"] == "declared_not_started"
    assert state["next_work_package_scope"]["read_only"] is True
    assert state["next_work_package_scope"]["candidate_or_group_disposition_controls"] is False
    assert "`expandable_deterministic_clusters`" in status
    assert "Declaration state:" in status
    assert "`declared_not_started`" in status


def test_clusters_and_every_underlying_candidate_are_native_expandable_disclosures() -> None:
    component = source(COMPONENT)
    styles = source(STYLES)

    assert 'data-expandable-clusters-contract="canonical-read-only-v1"' in component
    assert "function ClusterDisclosure" in component
    assert "function CandidateDisclosure" in component
    assert "<details" in component
    assert "<summary" in component
    assert "onToggle=" in component
    assert "event.currentTarget.open" in component
    assert "Expand cluster" in component
    assert "Collapse cluster" in component
    assert "Expand candidate" in component
    assert "Collapse candidate" in component
    assert "unit.candidates.map" in component
    assert "data-cluster-id={unit.id}" in component
    assert "data-candidate-id={candidateId(candidate)}" in component
    assert 'data-canonical-candidate-record="true"' in component
    assert "const [open, setOpen] = useState(false)" in component
    assert "open ? <div" in component
    assert "Cluster summaries never replace candidate evidence" in component
    assert "candidateDisclosure" in styles
    assert "clusterDisclosure" in styles
    assert ":focus-visible" in styles
    assert "[open]" in styles


def test_queue_uses_canonical_cluster_membership_and_fails_closed_on_parity_drift() -> None:
    component = source(COMPONENT)

    assert "register.review_workload_clusters" in component
    assert "triage.review_workload_clusters" in component
    assert "cluster.candidate_ids" in component
    assert "candidate.cluster_candidate_ids" in component
    assert "candidate.representative_candidate_id" in component
    assert "candidate.grouped_review_eligible" in component
    assert "candidate.homogeneous_evidence" in component
    assert "candidate.homogeneous_verdict" in component
    assert "underlying_candidate_disposition_required" in component
    assert "candidate.review_unit_id" in component
    assert "candidate.human_review_required" in component
    assert "candidate.human_disposition" in component
    assert "cluster.review_routing_classes" in component
    assert "queuedIds.length !== findings.length" in component
    assert "new Set(queuedIds).size !== findings.length" in component
    assert "triage.cluster_count" in component
    assert "triage.grouped_review_cluster_count" in component
    assert "triage.candidates_eligible_for_grouped_review" in component
    assert "triage.candidates_requiring_individual_human_attention" in component
    assert "triage.human_review_work_units" in component
    assert "Queue integrity check failed closed" in component
    assert "No candidate or cluster content is displayed" in component
    assert "model.integrityErrors.length ?" in component


def test_candidate_expansion_exposes_complete_retained_record_without_new_analysis_path() -> None:
    component = source(COMPONENT)
    api_routes = source(API_ROUTES)

    assert "Complete retained canonical candidate record" in component
    assert "JSON.stringify(candidate, null, 2)" in component
    assert "evidence, counterevidence, source context, dependency context" in component
    assert "technical_triage_rationale" in component
    assert "technical_triage_proof_gaps" in component
    assert "technical_triage_recommended_next_step" in component
    assert "technical_triage_model_or_version" in component
    assert "Evidence used" in component
    assert "Counterevidence" in component
    assert "reachability_assessment" in component
    assert "exploitability_assessment" in component
    assert "canonical_terminal_comprehensive_report_json" in component
    assert '"candidate_register": dict(register)' in api_routes
    assert "canonical_scanner_finding_register" in api_routes
    assert "report_package" not in component
    assert "pdf_base64" not in component


def test_wp2_remains_authenticated_read_only_and_does_not_absorb_later_work() -> None:
    component = source(COMPONENT)

    assert '"X-NICO-Admin-Token"' in component
    assert 'type="password"' in component
    assert "setAdminToken(\"\")" in component
    assert "localStorage" not in component
    assert "sessionStorage" not in component
    assert 'data-human-disposition-controls="absent"' in component
    assert 'data-client-delivery-authorization="absent"' in component
    assert "No candidate disposition, reviewer identity, risk acceptance, approval, score change" in component
    assert 'method: "POST"' not in component
    assert "quality_control_sampling" not in component
    assert "reviewer_workload_timer" not in component
