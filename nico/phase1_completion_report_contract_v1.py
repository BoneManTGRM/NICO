from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

SCHEMA = "nico.phase1-completion-bound-report.v1"

_EXPLICIT_APPROVAL_BOUNDARIES = (
    "Only an authorized reviewer may change the status to APPROVED FINAL",
    "Only an authorized human reviewer may approve the exact immutable artifacts",
    (
        "Only an authorized human reviewer may approve the exact immutable PDF, "
        "canonical JSON, and detached evidence manifest digests"
    ),
)

_UNIFIED_ACCEPTANCE_SCHEMAS = {
    "nico.unified_live_acceptance.v1",
    "nico.completed-run-two-pass-production-acceptance.v1",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_text(path: Path) -> tuple[str, int]:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)


def _one(pattern: str, text: str, label: str) -> int:
    match = re.search(pattern, text, re.I | re.S)
    if not match:
        raise ValueError(f"Source Comprehensive report is missing required Phase 1 evidence: {label}")
    return int(match.group(1))


def _require_score_separation(compact: str) -> None:
    """Require explicit proof that operational workload does not change numeric scores.

    Historical completion-bound reports used one fixed sentence. Current canonical
    reports expose the same truth through structured ``score_effect`` fields. Accept
    either representation, but fail closed if any structured field reports a value
    other than ``none`` or if no score-separation evidence is present.
    """

    normalized = compact.lower()
    structured_values = [
        match.group(1).lower().replace("-", "_")
        for match in re.finditer(
            r"`?(?:score_effect|technical_score_effect)`?\s*:\s*([a-z0-9_-]+)",
            normalized,
            re.I,
        )
    ]
    non_none = sorted({value for value in structured_values if value != "none"})
    if non_none:
        raise ValueError(
            "Source Comprehensive report contains non-none score-effect evidence: "
            + ", ".join(non_none)
        )
    if structured_values:
        return

    legacy_phrase = "no numeric technical-maturity or evidence-adjusted score effect"
    if legacy_phrase in normalized:
        return

    raise ValueError("Source Comprehensive report is missing no score gaming")


def extract_report(text: str, expected_sha: str) -> dict[str, Any]:
    compact = " ".join(text.split())
    if expected_sha not in compact:
        raise ValueError("Source Comprehensive report is not bound to the expected commit")
    required = {
        "technical/human separation": "Technical triage remains proposal-only",
        "blocked delivery": "client delivery remains blocked",
    }
    for label, phrase in required.items():
        if phrase.lower() not in compact.lower():
            raise ValueError(f"Source Comprehensive report is missing {label}")
    if not any(
        phrase.lower() in compact.lower()
        for phrase in _EXPLICIT_APPROVAL_BOUNDARIES
    ):
        raise ValueError("Source Comprehensive report is missing explicit approval")
    _require_score_separation(compact)

    report = {
        "fresh_required": _one(r"Current-evidence candidates requiring new technical triage:\s*(\d+)", compact, "fresh triage required"),
        "fresh_completed": _one(r"fresh automated triage completed=(\d+)", compact, "fresh triage completed"),
        "coverage_done": _one(r"Technical triage coverage:\s*(\d+)/\d+", compact, "triage coverage"),
        "coverage_total": _one(r"Technical triage coverage:\s*\d+/(\d+)", compact, "triage coverage total"),
        "carry_forward": _one(r"Exact carry-forward:\s*(\d+)", compact, "carry-forward"),
        "not_actionable": _one(r"not_actionable=(\d+)", compact, "not_actionable verdict"),
        "needs_review": _one(r"needs_review=(\d+)", compact, "needs_review verdict"),
        "confirmed": _one(r"confirmed=(\d+)", compact, "confirmed verdict"),
        "individual": _one(r"Individual human attention:\s*(\d+)", compact, "individual review"),
        "grouped": _one(r"grouped-review eligible candidates:\s*(\d+)", compact, "grouped review"),
        "clusters": _one(r"grouped human-review clusters:\s*(\d+)", compact, "cluster count"),
        "qc_pool": _one(r"quality-control pool:\s*(\d+)", compact, "quality-control pool"),
        "work_units": _one(r"Human review work units:\s*(\d+)", compact, "review work units"),
    }
    if report["fresh_required"] != report["fresh_completed"]:
        raise ValueError("Fresh-triage required/completed counts do not match")
    if report["coverage_done"] != report["coverage_total"]:
        raise ValueError("Technical triage coverage is incomplete")
    return report


def validate_external(
    acceptance: dict[str, Any],
    audit: dict[str, Any],
    release: dict[str, Any],
    status: dict[str, Any],
    expected_sha: str,
) -> None:
    if (
        acceptance.get("artifact_schema") not in _UNIFIED_ACCEPTANCE_SCHEMAS
        or acceptance.get("status") != "passed"
    ):
        raise ValueError("Unified Production Acceptance did not pass")
    if acceptance.get("expected_deployed_sha") != expected_sha:
        raise ValueError("Unified Production Acceptance is bound to a different SHA")
    if acceptance.get("passes_required") != 2 or acceptance.get("passes_completed") != 2:
        raise ValueError("Two consecutive deployed Comprehensive passes were not completed")
    proof = acceptance.get("proof")
    if not isinstance(proof, dict) or not proof or not all(value is True for value in proof.values()):
        raise ValueError("Unified Production Acceptance proof is incomplete")

    if audit.get("artifact_schema") != "nico.phase1-structured-artifact-audit.v1" or audit.get("status") != "passed":
        raise ValueError("Phase 1 structured candidate-artifact audit did not pass")
    if audit.get("commit_sha") != expected_sha or audit.get("errors") not in ([], None):
        raise ValueError("Phase 1 structured audit is not clean for the expected SHA")
    if audit.get("candidate_register_sha256_expected") != audit.get("candidate_register_sha256_observed"):
        raise ValueError("Candidate-register digest parity failed")
    if audit.get("cluster_integrity_error_count") != 0 or audit.get("score_effect") != "none":
        raise ValueError("Cluster integrity or score-separation audit failed")
    if audit.get("human_review_required") is not True or audit.get("client_delivery_allowed") is not False:
        raise ValueError("Human approval/client-delivery boundary was weakened")

    if release.get("artifact_schema") != "nico.frontend_production_release_identity.v1" or release.get("status") != "passed":
        raise ValueError("Exact frontend release identity did not pass")
    final_release = release.get("final_release_observation") or {}
    if release.get("expected_sha") != expected_sha or final_release.get("release_sha") != expected_sha:
        raise ValueError("Frontend release identity is bound to a different SHA")

    if status.get("artifact_schema") != "nico.phase1-current-head-status.v1" or status.get("commit_sha") != expected_sha:
        raise ValueError("Current-head status snapshot is invalid")
    contexts = status.get("contexts") if isinstance(status.get("contexts"), dict) else {}
    for name in status.get("required_contexts") or []:
        if (contexts.get(name) or {}).get("state") != "success":
            raise ValueError(f"Required current-head context is not successful: {name}")


def dod_rows(report: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [
        ("1. Fresh triage for new/evidence-changed candidates", "PASS", f"{report['fresh_completed']}/{report['fresh_required']} freshly triaged"),
        ("2. Uncertain candidates safely become needs_review", "PASS", f"needs_review={report['needs_review']}; no automated guessing"),
        ("3. Stable unchanged evidence retains valid prior analysis", "PASS", f"exact carry-forward={report['carry_forward']}"),
        ("4. Clustering reduces repetitive review without hiding candidates", "PASS", f"grouped={report['grouped']}; clusters={report['clusters']}"),
        ("5. True reviewer exception workload is calculated", "PASS", f"individual={report['individual']}; work units={report['work_units']}; QC pool={report['qc_pool']}"),
        ("6. Technical triage remains separate from human disposition", "PASS", "proposal-only technical triage; human dispositions pending"),
        ("7. Human approval remains explicit", "PASS", "authorized human approval required; client delivery blocked"),
        ("8. No score or finding semantics were gamed", "PASS", "candidate workload has no numeric score effect"),
        ("9. Required current-head checks pass", "PASS", "Vercel, Railway, Mobile, iOS WebKit, and Two-Service acceptance all successful"),
    ]
