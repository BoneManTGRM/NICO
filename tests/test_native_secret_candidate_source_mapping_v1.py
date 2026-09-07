from copy import deepcopy

import pytest

from nico import comprehensive_native_providers_v5 as subject


ASSESSED = "a" * 40
HISTORY = "b" * 40


def native(tool, path="qualification/synthetic.txt", line=7, commit=HISTORY):
    if tool == "gitleaks":
        return {
            "File": path, "StartLine": line, "StartColumn": 3,
            "RuleID": "synthetic-secret-rule", "Description": "Synthetic credential candidate",
            "Commit": commit, "Match": "[REDACTED]",
        }
    return {
        "SourceMetadata": {"Data": {"Git": {"file": path, "line": line, "commit": commit}}},
        "DetectorName": "synthetic-secret-rule", "Verified": False,
    }


def register(tool, findings, material=0):
    return subject.build_canonical_scanner_finding_register({
        "scanner_results": [{"tool": tool, "category": "secret", "findings": findings}],
        "finding_summary": {"by_tool": {tool: {
            "raw": len(findings), "review_required": len(findings) - material,
            "material": material, "approved_or_nonblocking": 0, "excluded_test_only": 0,
        }}},
    }, ASSESSED)


@pytest.mark.parametrize("tool", ["gitleaks", "trufflehog"])
def test_native_secret_coordinates_and_history_identity_survive_candidate_expansion(tool):
    first = native(tool)
    second = native(tool, path="qualification/other.txt", line=19)
    third = native(tool, commit="c" * 40)
    inputs = [first, deepcopy(first), second, third]
    before = deepcopy(inputs)
    result = register(tool, inputs)
    assert inputs == before
    assert result["status"] == "complete"
    assert result["totals"]["raw"] == len(result["findings"]) == 4
    rows = result["findings"]
    assert {(r["source_path"], r["line"]) for r in rows} == {
        ("qualification/synthetic.txt", 7), ("qualification/other.txt", 19),
    }
    assert {r["rule_id"] for r in rows} == {"synthetic-secret-rule"}
    assert {r["exact_commit_sha"] for r in rows} == {ASSESSED}
    assert {r["source_commit_sha"] for r in rows} == {HISTORY, "c" * 40}
    assert all(r["evidence_quality"] == "exact_source" for r in rows)
    assert len({r["candidate_id"] for r in rows}) == 4
    assert len({r["duplicate_group_id"] for r in rows}) == 3
    duplicate = [r for r in rows if r.get("aggregate_candidate_population") == 2]
    assert len(duplicate) == 2
    assert {r["aggregate_candidate_ordinal"] for r in duplicate} == {1, 2}
    assert all(r["source_path"] == "qualification/synthetic.txt" and r["source_commit_sha"] == HISTORY for r in duplicate)


@pytest.mark.parametrize("tool", ["gitleaks", "trufflehog"])
def test_fixture_path_does_not_dispose_of_native_secret_evidence(tool):
    result = register(tool, [native(tool, path="tests/fixtures/synthetic.txt")])
    assert result["status"] == "complete"
    assert result["totals"]["review_required"] == 1
    assert result["totals"]["excluded_test_only"] == 0
    assert result["findings"][0]["human_review_required"] is True


def test_verified_secret_in_fixture_remains_material():
    finding = native("trufflehog", path="tests/fixtures/synthetic.txt")
    finding["Verified"] = True
    result = register("trufflehog", [finding], material=1)
    assert result["status"] == "complete"
    assert result["totals"]["material"] == 1
    assert result["findings"][0]["disposition"] == "verified_material"


@pytest.mark.parametrize("verified", [False, True])
def test_scanner_summary_keeps_secret_fixture_observations_for_review(verified):
    from nico.snapshot_scanner_worker import _tool_triage

    counts = _tool_triage({
        "tool": "trufflehog", "category": "secret",
        "findings": [{"source_path": "tests/fixtures/synthetic.txt", "Verified": verified}],
    })
    assert counts["raw"] == 1
    assert counts["excluded_test_only"] == 0
    assert counts["material"] == int(verified)
    assert counts["review_required"] == int(not verified)


@pytest.mark.parametrize("tool", ["gitleaks", "trufflehog"])
def test_absent_native_metadata_is_not_fabricated(tool):
    row = register(tool, [{}])["findings"][0]
    assert row["source_path"] == ""
    assert row["line"] is None
    assert row["rule_id"] == "unclassified"
    assert not row.get("source_commit_sha")
    assert row["evidence_quality"] == "payload_without_source"
    assert row["disposition"] == "review_required"


@pytest.mark.parametrize("tool", ["gitleaks", "trufflehog"])
@pytest.mark.parametrize("normalized_fields", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_native_secret_context_and_triage_stay_with_source_history(tool, normalized_fields, reverse):
    from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence
    from nico.candidate_technical_triage_v1 import apply_candidate_technical_triage

    rows = []
    for commit, synthetic in [("c" * 40, False), (HISTORY, True)]:
        raw = native(tool, path="tests/fixtures/synthetic.txt", commit=commit)
        raw.update({"Verified": False, "synthetic": synthetic})
        if normalized_fields:
            raw.update({"source_path": "tests/fixtures/synthetic.txt", "line": 7,
                        "rule_id": "synthetic-secret-rule"})
        rows.append(raw)
    if reverse:
        rows.reverse()
    before = deepcopy(rows)
    canonical = register(tool, rows)
    enriched = enrich_canonical_candidate_evidence(canonical, {
        "scanner_results": [{"tool": tool, "category": "secret", "findings": rows}],
    })
    assert rows == before
    assert enriched["totals"] == canonical["totals"]
    assert enriched["candidate_evidence_context"]["records_enriched"] == 2
    assert enriched["candidate_evidence_context"]["records_without_matching_raw_context"] == 0
    by_commit = {r["source_commit_sha"]: r for r in enriched["findings"]}
    assert by_commit["c" * 40]["deterministic_evidence"]["synthetic"] is False
    assert by_commit[HISTORY]["deterministic_evidence"]["synthetic"] is True
    assert all(r["deterministic_evidence"]["verified"] is False for r in by_commit.values())
    triaged = apply_candidate_technical_triage(enriched, triage={"s": "synthetic-empty-triage", "r": []})
    by_commit = {r["source_commit_sha"]: r for r in triaged["findings"]}
    assert by_commit["c" * 40]["technical_triage_verdict"] == "needs_review"
    assert all(r["human_approval_status"] == "pending" for r in by_commit.values())
    assert all(r["technical_triage_client_delivery_allowed"] is False for r in by_commit.values())


@pytest.mark.parametrize("tool", ["gitleaks", "trufflehog"])
def test_native_secret_context_does_not_borrow_missing_source_history(tool):
    from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence

    known = native(tool)
    canonical = register(tool, [known])
    unknown = native(tool, commit="")
    unknown.update({"source_path": "qualification/synthetic.txt", "line": 7,
                    "rule_id": "synthetic-secret-rule", "synthetic": True})
    enriched = enrich_canonical_candidate_evidence(canonical, {
        "scanner_results": [{"tool": tool, "category": "secret", "findings": [unknown]}],
    })
    assert enriched["candidate_evidence_context"]["records_without_matching_raw_context"] == 1
    assert "synthetic" not in enriched["findings"][0].get("deterministic_evidence", {})


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_same_source_context_stays_unresolved(reverse):
    from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence
    from nico.candidate_technical_triage_v1 import apply_candidate_technical_triage

    real = native("trufflehog", path="tests/fixture.txt")
    real.update({"Verified": True, "synthetic": False})
    synthetic = deepcopy(real)
    synthetic.update({"Verified": False, "synthetic": True})
    rows = [real, synthetic]
    if reverse:
        rows.reverse()
    canonical = register("trufflehog", rows, material=1)
    enriched = enrich_canonical_candidate_evidence(canonical, {
        "scanner_results": [{"tool": "trufflehog", "category": "secret", "findings": rows}],
    })
    assert enriched["totals"] == canonical["totals"]
    assert enriched["candidate_evidence_context"]["records_with_ambiguous_raw_context"] == 2
    assert enriched["candidate_evidence_context"]["status"] == "partial"
    assert all(r["candidate_evidence_context_status"] == "ambiguous" for r in enriched["findings"])
    assert all(not r.get("deterministic_evidence") for r in enriched["findings"])
    triaged = apply_candidate_technical_triage(enriched, triage={"s": "synthetic-empty-triage", "r": []})
    assert all(r["technical_triage_verdict"] == "needs_review" for r in triaged["findings"])
    assert all("ambiguous_raw_context_binding" in r["technical_triage_proof_gaps"] for r in triaged["findings"])
    assert sum(r["disposition"] == "verified_material" for r in triaged["findings"]) == 1
    # Even a formerly reusable technical proposal cannot override a newly
    # ambiguous binding. Canonical scanner dispositions remain retained.
    for row in enriched["findings"]:
        row.update({"lineage_status": "carried_forward_exact", "prior_candidate_id": "OLD-SYNTHETIC"})
    prior = {
        "s": "nico.candidate-technical-triage.v1", "c": "d" * 40,
        "q": {"fixture": ["not_actionable", "high", "approved_or_nonblocking",
                          "retained_evidence", "Synthetic prior proposal", "Proposal only",
                          "Inspect retained evidence", [], ""]},
        "x": [["OLD-SYNTHETIC", "fixture", None]],
    }
    reused = apply_candidate_technical_triage(enriched, triage=prior)
    assert all(r["technical_triage_verdict"] == "needs_review" for r in reused["findings"])
    assert all(r["technical_triage_status"] == "fresh_proposal" for r in reused["findings"])


@pytest.mark.parametrize("tool", ["gitleaks", "trufflehog"])
def test_case_sensitive_secret_sources_are_not_merged_or_cross_enriched(tool):
    from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence

    rows = []
    for path, synthetic in [("tests/a.txt", True), ("tests/A.txt", False)]:
        raw = native(tool, path=path)
        raw.update({"Verified": False, "synthetic": synthetic})
        rows.append(raw)
    canonical = register(tool, rows)
    assert {r["source_path"] for r in canonical["findings"]} == {"tests/a.txt", "tests/A.txt"}
    assert len({r["raw_fingerprint"] for r in canonical["findings"]}) == 2
    enriched = enrich_canonical_candidate_evidence(canonical, {
        "scanner_results": [{"tool": tool, "category": "secret", "findings": rows}],
    })
    by_path = {r["source_path"]: r for r in enriched["findings"]}
    assert by_path["tests/a.txt"]["deterministic_evidence"]["synthetic"] is True
    assert by_path["tests/A.txt"]["deterministic_evidence"]["synthetic"] is False


def test_identical_duplicate_secret_context_can_be_enriched_safely():
    from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence

    raw = native("trufflehog")
    raw["synthetic"] = False
    rows = [raw, deepcopy(raw)]
    canonical = register("trufflehog", rows)
    enriched = enrich_canonical_candidate_evidence(canonical, {
        "scanner_results": [{"tool": "trufflehog", "category": "secret", "findings": rows}],
    })
    assert enriched["candidate_evidence_context"]["records_enriched"] == 2
    assert all(r["deterministic_evidence"]["synthetic"] is False for r in enriched["findings"])
