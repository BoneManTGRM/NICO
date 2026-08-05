from __future__ import annotations

from copy import deepcopy

from nico.client_readiness_evidence_intake import (
    SECTION_DEFINITIONS,
    build_client_evidence_register,
    client_evidence_gate,
    client_evidence_intake_template,
)


SHA = "a" * 40
DIGEST = "e" * 64
RUN_ID = "comprun_client_ready"


def _authority(identity: str = "authorized-reviewer") -> dict:
    return {
        "identity": identity,
        "role": "client evidence reviewer",
        "authorized": True,
        "authorization_basis": "engagement-approval-matrix",
        "recorded_at": "2026-08-05T18:00:00Z",
    }


def _evidence(section_id: str) -> dict:
    return {
        "evidence_id": f"evidence-{section_id}",
        "source_type": "client_supplied_artifact",
        "submitted_by": "client-owner",
        "submitted_at": "2026-08-05T17:00:00Z",
        "scope": f"Evidence for {section_id}",
        "artifact_sha256": DIGEST,
    }


def _completed_sections() -> list[dict]:
    template = client_evidence_intake_template(repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)
    sections = deepcopy(template["sections"])
    for section in sections:
        section["status"] = "assessed"
        section["evidence"] = [_evidence(section["section_id"])]
        section["conclusion"] = "The supplied evidence was reviewed within the stated scope."
        section["reviewer"] = _authority()
    return sections


def test_template_contains_all_eight_sections_pending_without_invented_evidence() -> None:
    template = client_evidence_intake_template(repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)

    assert len(template["sections"]) == 8
    assert {item["section_id"] for item in template["sections"]} == set(SECTION_DEFINITIONS)
    assert all(item["status"] == "pending" for item in template["sections"])
    assert all(item["evidence"] == [] for item in template["sections"])
    assert template["automation_may_complete_client_evidence"] is False


def test_pending_template_fails_closed() -> None:
    sections = client_evidence_intake_template()["sections"]

    register = build_client_evidence_register(
        sections,
        repository="BoneManTGRM/NICO",
        commit_sha=SHA,
        run_id=RUN_ID,
    )

    assert register["status"] == "blocked"
    assert len(register["pending_section_ids"]) == 8
    assert client_evidence_gate(
        register,
        expected_repository="BoneManTGRM/NICO",
        expected_commit_sha=SHA,
        expected_run_id=RUN_ID,
    )["status"] == "blocked"


def test_all_eight_assessed_sections_pass_without_authorizing_delivery() -> None:
    register = build_client_evidence_register(
        _completed_sections(),
        repository="BoneManTGRM/NICO",
        commit_sha=SHA,
        run_id=RUN_ID,
    )
    gate = client_evidence_gate(
        register,
        expected_repository="BoneManTGRM/NICO",
        expected_commit_sha=SHA,
        expected_run_id=RUN_ID,
    )

    assert register["status"] == "passed"
    assert register["section_count"] == 8
    assert gate["status"] == "passed"
    assert gate["client_delivery_allowed"] is False


def test_assessed_section_requires_retained_evidence_and_authorized_reviewer() -> None:
    sections = _completed_sections()
    sections[0]["evidence"] = []
    sections[0]["reviewer"]["authorized"] = False

    register = build_client_evidence_register(sections, repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)
    errors = " ".join(register["invalid_sections"][0]["errors"])

    assert register["status"] == "blocked"
    assert "retained evidence" in errors
    assert "reviewer.authorized must be true" in errors


def test_limited_section_requires_explicit_limitations_and_authorized_acceptance() -> None:
    sections = _completed_sections()
    section = sections[0]
    section["status"] = "limited"
    section["limitations"] = []
    section["accepted_limitations"] = {}

    blocked = build_client_evidence_register(sections, repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)
    errors = " ".join(blocked["invalid_sections"][0]["errors"])
    assert "explicit limitations" in errors
    assert "accepted_limitations.identity" in errors

    section["limitations"] = ["Only Safari on the approved iPhone device was tested."]
    section["accepted_limitations"] = {**_authority("authorized-limitation-owner"), "scope": "Exact Functional QA section"}
    complete = build_client_evidence_register(sections, repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)
    assert complete["status"] == "passed"


def test_not_applicable_requires_justification_and_authorized_scope() -> None:
    sections = _completed_sections()
    section = sections[-1]
    section["status"] = "not_applicable"
    section["evidence"] = []
    section["justification"] = ""
    section["not_applicable_authorization"] = {}

    blocked = build_client_evidence_register(sections, repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)
    errors = " ".join(blocked["invalid_sections"][0]["errors"])
    assert "requires a justification" in errors
    assert "not_applicable_authorization.identity" in errors

    section["justification"] = "The engagement excludes commercial staffing and cost advice."
    section["not_applicable_authorization"] = {**_authority("authorized-scope-owner"), "scope": "Exact engagement scope"}
    complete = build_client_evidence_register(sections, repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)
    assert complete["status"] == "passed"


def test_missing_duplicate_or_unexpected_sections_fail_closed() -> None:
    sections = _completed_sections()
    sections.pop()
    sections.append(deepcopy(sections[0]))
    sections.append(
        {
            "section_id": "invented_section",
            "title": "Invented",
            "status": "pending",
        }
    )

    register = build_client_evidence_register(sections, repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)
    blockers = " ".join(register["blockers"])

    assert register["status"] == "blocked"
    assert "duplicate client evidence sections" in blockers
    assert "missing client evidence sections" in blockers
    assert "unexpected client evidence sections" in blockers


def test_evidence_ids_and_artifact_digests_must_be_valid() -> None:
    sections = _completed_sections()
    section = sections[0]
    duplicate = deepcopy(section["evidence"][0])
    duplicate["artifact_sha256"] = "bad"
    section["evidence"].append(duplicate)

    register = build_client_evidence_register(sections, repository="BoneManTGRM/NICO", commit_sha=SHA, run_id=RUN_ID)
    errors = " ".join(register["invalid_sections"][0]["errors"])

    assert register["status"] == "blocked"
    assert "artifact_sha256" in errors
    assert "duplicate evidence_id" in errors


def test_gate_rejects_stale_repository_commit_or_run_binding() -> None:
    register = build_client_evidence_register(
        _completed_sections(),
        repository="BoneManTGRM/NICO",
        commit_sha=SHA,
        run_id=RUN_ID,
    )

    gate = client_evidence_gate(
        register,
        expected_repository="Other/Repo",
        expected_commit_sha="c" * 40,
        expected_run_id="different-run",
    )

    assert gate["status"] == "blocked"
    blockers = " ".join(gate["blockers"])
    assert "repository identity" in blockers
    assert "commit identity" in blockers
    assert "run identity" in blockers
