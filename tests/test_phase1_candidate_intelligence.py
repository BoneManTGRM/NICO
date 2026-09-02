from __future__ import annotations

from copy import deepcopy

from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence
from nico.candidate_lineage_migration_v1 import apply_candidate_lineage, lineage_keys
from nico.candidate_technical_triage_v1 import apply_candidate_technical_triage

SUBJECT = {
    "repository": "BoneManTGRM/NICO",
    "project_id": "nico",
    "workspace_id": "ws-1",
    "assessment_target_id": "repo-root",
}


def candidate(
    candidate_id: str,
    *,
    category: str = "static",
    scanner: str = "semgrep",
    rule: str = "rule.x",
    path: str = "nico/a.py",
    line: int = 10,
    evidence: str = "hit",
    severity: str = "medium",
    context: dict | None = None,
    occurrence_count: int = 1,
) -> dict:
    value = {
        "finding_id": candidate_id,
        "candidate_id": candidate_id,
        "category": category,
        "scanner": scanner,
        "rule_id": rule,
        "source_path": path,
        "line": line,
        "evidence": evidence,
        "severity": severity,
        "confidence": "high",
        "evidence_quality": "exact_source",
        "occurrence_count": occurrence_count,
        "disposition": "review_required",
        "human_disposition": "pending",
        "human_approval_status": "pending",
    }
    if context is not None:
        value["deterministic_evidence"] = context
    return value


def baseline_for(prior: list[dict], subject: dict | None = None) -> dict:
    rows = []
    for item in prior:
        keys = lineage_keys(item)
        rows.append(
            [
                keys["exact"],
                keys["semantic"],
                keys["group"],
                keys["line"],
                item["candidate_id"],
                "source_review_required",
                "OLD-CLUSTER",
            ]
        )
    identity = subject or SUBJECT
    return {
        "s": "nico.candidate-lineage-baseline.v2",
        "n": len(rows),
        "a": "none",
        "r": identity["repository"],
        "p": identity.get("project_id"),
        "w": identity.get("workspace_id"),
        "t": identity.get("assessment_target_id"),
        "c": "prior-sha",
        "x": rows,
    }


def register(findings: list[dict], subject: dict | None = None) -> dict:
    return {
        "assessment_subject": deepcopy(subject or SUBJECT),
        "findings": deepcopy(findings),
        "totals": {
            "raw": sum(item.get("occurrence_count", 1) for item in findings)
        },
    }


def retained_triage(candidate_id: str, verdict: str = "not_actionable") -> dict:
    proposal = (
        "approved_or_nonblocking" if verdict == "not_actionable" else "review_required"
    )
    rank = None if verdict == "not_actionable" else 1
    return {
        "s": "nico.candidate-technical-triage.v1",
        "c": "prior-sha",
        "n": 1,
        "q": {
            "retained": [
                verdict,
                "high",
                proposal,
                "retained_evidence",
                "Prior evidence supported this proposal.",
                "Proposal only.",
                "Spot check retained evidence.",
                [],
                "",
            ]
        },
        "x": [[candidate_id, "retained", rank]],
    }


def analyze(
    current: list[dict],
    prior: list[dict] = [],
    *,
    triage: dict | None = None,
    subject: dict | None = None,
    baseline_subject: dict | None = None,
) -> dict:
    lined = apply_candidate_lineage(
        register(current, subject),
        baseline=baseline_for(prior, baseline_subject),
    )
    empty = {
        "s": "nico.candidate-technical-triage.v1",
        "c": "prior-sha",
        "n": 0,
        "q": {},
        "x": [],
    }
    return apply_candidate_technical_triage(lined, triage=triage or empty)


def test_new_and_evidence_changed_candidates_receive_fresh_fail_safe_triage() -> None:
    new = candidate(
        "NEW",
        category="dependency",
        scanner="osv-scanner",
        rule="GHSA-1",
        path="requirements.lock",
        context={
            "scanned_package": {
                "name": "pillow",
                "version": "11.3.0",
                "ecosystem": "PyPI",
                "manifest_path": "requirements.lock",
            },
            "installed_version_affected": False,
            "dependency_scope": "production",
        },
    )
    fresh = analyze([new])["findings"][0]
    assert fresh["lineage_status"] == "newly_observed"
    assert fresh["technical_triage_status"] == "fresh_proposal"
    assert fresh["technical_triage_verdict"] == "not_actionable"

    prior = candidate("OLD", evidence="old hit", line=10)
    changed = candidate("CURRENT", evidence="changed evidence", line=11)
    result = analyze([changed], [prior], triage=retained_triage("OLD"))
    finding = result["findings"][0]
    assert finding["lineage_status"] == "carried_forward_evidence_changed"
    assert finding["technical_triage_status"] == "fresh_proposal"
    assert finding["technical_triage_source"] != "retained_prior_nico_recommendation"
    assert finding["technical_triage_verdict"] == "needs_review"
    assert result["technical_triage"]["technical_triage_coverage_pct"] == 100.0


def test_stable_lineage_retains_proposal_without_human_authority() -> None:
    result = analyze(
        [candidate("CURRENT")],
        [candidate("OLD")],
        triage=retained_triage("OLD"),
    )
    finding = result["findings"][0]
    assert finding["technical_triage_status"] == "imported_proposal"
    assert finding["technical_triage_verdict"] == "not_actionable"
    assert finding["review_routing_class"] == "STABLE_CARRY_FORWARD"
    assert finding["disposition"] == "review_required"
    assert finding["human_disposition"] == "pending"
    assert finding["human_approval_status"] == "pending"
    assert result["technical_triage"]["human_disposition_created"] is False
    assert result["technical_triage"]["reviewer_identity_created"] is False
    assert result["technical_triage"]["risk_acceptance_created"] is False
    assert result["technical_triage"]["client_delivery_allowed"] is False


def test_dependency_identity_uses_actual_scanned_package_not_nested_advisory() -> None:
    value = candidate(
        "DEP",
        category="dependency",
        scanner="osv-scanner",
        rule="GHSA-X",
        path="uv.lock",
        context={
            "scanned_package": {
                "name": "actual-lib",
                "version": "2.0.0",
                "ecosystem": "PyPI",
            },
            "installed_version_affected": False,
            "nested_affected_package": "different-advisory-lib",
        },
    )
    finding = analyze([value])["findings"][0]
    assert finding["dependency_package"] == "actual-lib"
    assert finding["dependency_version"] == "2.0.0"
    assert finding["technical_triage_verdict"] == "not_actionable"
    assert (
        "nested_advisory_package_ignored=different-advisory-lib"
        in finding["counterevidence"]
    )

    unresolved = analyze(
        [
            candidate(
                "MISSING",
                category="dependency",
                scanner="osv-scanner",
                rule="GHSA-Y",
                context={},
            )
        ]
    )["findings"][0]
    assert unresolved["technical_triage_verdict"] == "needs_review"
    assert "actual_scanned_package" in unresolved["proof_gaps"]


def test_secret_and_static_triage_respect_evidence_boundaries() -> None:
    verified = candidate(
        "SECRET",
        category="secret",
        scanner="trufflehog",
        rule="token",
        path="tests/example.env",
        severity="critical",
        context={"verified": True, "synthetic": True, "scope": "test"},
    )
    secret = analyze([verified])["findings"][0]
    assert secret["technical_triage_verdict"] == "confirmed"
    assert secret["rationale_code"] == "verified_secret"
    assert secret["review_routing_class"] == "CRITICAL_ATTENTION"
    assert (
        "fixture_or_example_context_does_not_override_verification"
        in secret["counterevidence"]
    )

    noise = candidate(
        "NOISE",
        category="static",
        path="tests/example.py",
        context={
            "executable_code": False,
            "comment_or_string": True,
            "scope": "test",
        },
    )
    static_noise = analyze([noise])["findings"][0]
    assert static_noise["technical_triage_verdict"] == "not_actionable"
    assert static_noise["rationale_code"] == "static_nonexecutable_noise"

    generic = candidate(
        "GENERIC",
        category="static",
        severity="critical",
        context={
            "executable_code": True,
            "scope": "production",
            "first_party_reachable": True,
            "mitigated": False,
        },
    )
    static_generic = analyze([generic])["findings"][0]
    assert static_generic["technical_triage_verdict"] == "needs_review"
    assert "realistic_exploitability" in static_generic["proof_gaps"]
    assert "supported_security_boundary" in static_generic["proof_gaps"]


def test_context_enrichment_preserves_safe_context_and_boolean_meaning() -> None:
    canonical = register(
        [
            candidate(
                "RAW",
                category="secret",
                scanner="trufflehog",
                rule="token",
                path="tests/example.env",
            )
        ]
    )
    scan = {
        "scanner_results": [
            {
                "scanner_name": "trufflehog",
                "category": "secret",
                "findings": [
                    {
                        "id": "token",
                        "path": "tests/example.env",
                        "line": 10,
                        "verified": "false",
                        "synthetic": "synthetic",
                        "secret": "must-not-retain",
                    }
                ],
            }
        ]
    }
    enriched = enrich_canonical_candidate_evidence(canonical, scan)
    evidence = enriched["findings"][0]["deterministic_evidence"]
    assert evidence["verified"] is False
    assert evidence["synthetic"] is True
    assert "secret" not in evidence
    assert enriched["candidate_evidence_context"]["candidate_counts_changed"] is False


def test_clustering_preserves_every_candidate_and_exact_occurrence_counts() -> None:
    context = {
        "executable_code": False,
        "comment_or_string": True,
        "scope": "test",
    }
    first = candidate(
        "A", path="tests/fixture_1.py", line=10, context=context, occurrence_count=2
    )
    second = candidate(
        "B", path="tests/fixture_2.py", line=20, context=context, occurrence_count=3
    )
    one = analyze([first, second])
    two = analyze([second, first])
    assert {item["candidate_id"] for item in one["findings"]} == {"A", "B"}
    assert one["technical_triage"]["total_candidates"] == 5
    assert one["technical_triage"]["cluster_count"] == 1
    assert {item["cluster_id"] for item in one["findings"]} == {
        item["cluster_id"] for item in two["findings"]
    }
    assert all(item["cluster_size"] == 5 for item in one["findings"])
    assert all(item["grouped_review_eligible"] is True for item in one["findings"])
    assert {item["source_path"] for item in one["findings"]} == {
        "tests/fixture_1.py",
        "tests/fixture_2.py",
    }


def test_workload_metrics_are_deterministic_and_not_security_scores() -> None:
    stable = candidate("STABLE")
    prior = candidate("OLD")
    uncertain = candidate(
        "REVIEW",
        category="dependency",
        scanner="osv-scanner",
        rule="GHSA-U",
        context={},
    )
    qc = candidate(
        "QC",
        path="tests/example.py",
        context={
            "executable_code": False,
            "comment_or_string": True,
            "scope": "test",
        },
    )
    result = analyze([stable, uncertain, qc], [prior], triage=retained_triage("OLD"))
    metrics = result["technical_triage"]["workload_metrics"]
    assert metrics == {key: result["technical_triage"][key] for key in metrics}
    assert metrics["total_candidates"] == 3
    assert metrics["technical_triage_completed"] == 3
    assert metrics["technical_triage_pending"] == 0
    assert metrics["not_actionable_count"] == 2
    assert metrics["needs_review_count"] == 1
    assert metrics["stable_carry_forward_count"] == 1
    assert metrics["candidates_requiring_individual_human_attention"] == 1
    assert metrics["quality_control_sample_pool"] == 1
    assert result["technical_triage"]["score_effect"] == (
        "none_canonical_dispositions_and_totals_unchanged"
    )


def test_subject_identity_isolation_is_fail_closed_without_false_tombstones() -> None:
    prior = candidate("OLD")
    current = candidate("CURRENT")
    for changed in (
        {**SUBJECT, "repository": "OtherOrg/OtherRepo"},
        {**SUBJECT, "project_id": "other-project"},
        {**SUBJECT, "workspace_id": "other-workspace"},
        {**SUBJECT, "assessment_target_id": "subdir"},
    ):
        result = analyze([current], [prior], subject=changed)
        lineage = result["candidate_lineage"]
        assert lineage["assessment_subject_match"] is False
        assert lineage["carried_forward_total"] == 0
        assert lineage["no_longer_observed"] == 0
        assert lineage["tombstones"] == []
        assert result["findings"][0]["lineage_status"] == "newly_observed"

    unscoped = apply_candidate_lineage(
        {"findings": [current], "totals": {"raw": 1}},
        baseline=baseline_for([prior]),
    )
    assert unscoped["candidate_lineage"]["assessment_subject_match_reason"] == (
        "current_subject_identity_missing"
    )


def test_string_status_domains_and_retained_proof_fields_are_preserved() -> None:
    secret = candidate(
        "SECRET-STRING",
        category="secret",
        scanner="trufflehog",
        rule="token",
        path="tests/example.env",
        context={"verified": "false", "synthetic": "synthetic", "scope": "test"},
    )
    assert analyze([secret])["findings"][0]["technical_triage_verdict"] == (
        "not_actionable"
    )

    dependency = candidate(
        "DEP-FIXED",
        category="dependency",
        scanner="osv-scanner",
        rule="GHSA-X",
        path="uv.lock",
        context={
            "scanned_package": {
                "name": "actual-lib",
                "version": "2.0.0",
                "ecosystem": "PyPI",
            },
            "current_resolution_fixed": "fixed",
        },
    )
    dep = analyze([dependency])["findings"][0]
    assert dep["technical_triage_verdict"] == "not_actionable"
    assert dep["rationale_code"] == "dependency_resolution_not_affected"

    source = retained_triage("OLD", verdict="needs_review")
    source["q"]["retained"][7] = ["runtime_configuration"]
    retained = analyze(
        [candidate("CURRENT")],
        [candidate("OLD")],
        triage=source,
    )["findings"][0]
    assert retained["proof_gaps"] == ["runtime_configuration"]
    assert retained["rationale_code"] == "retained"
    assert retained["recommended_next_step"] == "Spot check retained evidence."
    assert retained["evidence_used"]


def test_repeated_analysis_and_one_thousand_candidate_batch_are_deterministic() -> None:
    values = [
        candidate(
            "A",
            category="dependency",
            scanner="osv-scanner",
            rule="GHSA-A",
            context={
                "scanned_package": {"name": "a", "version": "1", "ecosystem": "PyPI"},
                "installed_version_affected": False,
            },
        ),
        candidate("B", category="secret", scanner="gitleaks", rule="generic", context={}),
    ]
    first = analyze(values)
    second = analyze(values)
    assert first["canonical_digest_sha256"] == second["canonical_digest_sha256"]
    assert first["technical_triage"]["workload_metrics"] == second["technical_triage"]["workload_metrics"]

    context = {
        "executable_code": False,
        "comment_or_string": True,
        "scope": "test",
    }
    batch = [
        candidate(
            f"C-{index}",
            path=f"tests/fixture_{index}.py",
            line=index + 1,
            context=context,
        )
        for index in range(1000)
    ]
    metrics = analyze(batch)["technical_triage"]
    assert metrics["total_candidates"] == 1000
    assert metrics["technical_triage_completed"] == 1000
    assert metrics["technical_triage_coverage_pct"] == 100.0
    assert metrics["candidates_requiring_individual_human_attention"] == 0
    assert metrics["algorithm_version"] == "nico.deterministic-contextual-triage.v2"
