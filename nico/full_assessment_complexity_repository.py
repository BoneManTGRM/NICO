from __future__ import annotations

import hashlib
import json
from typing import Any

from nico.full_assessment_complexity_evidence import collect_complexity_evidence
from nico.hosted_assessment import GitHubAssessmentClient, fetch_repository_profile
from nico.storage import STORE, StorageAdapter


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _evidence_id(run_id: str, repository: str) -> str:
    digest = hashlib.sha256(f"full-assessment-complexity|{run_id}|{repository}".encode("utf-8")).hexdigest()[:20]
    return f"evidence_complexity_{digest}"


def _safe_note(error: str | None) -> str:
    lowered = str(error or "").lower()
    if "401" in lowered or "403" in lowered:
        return "Complexity source evidence was unavailable because the GitHub credential or installation lacks required read access."
    if "404" in lowered:
        return "Complexity source evidence was unavailable through the authorized GitHub API scope."
    if "429" in lowered or "rate" in lowered:
        return "Complexity source evidence was unavailable because the GitHub API rate limit was reached."
    return "Complexity source evidence was unavailable through the GitHub API."


def _persist(bundle: dict[str, Any], store: StorageAdapter) -> dict[str, Any]:
    evidence_id = str(bundle["evidence_id"])
    encoded = json.dumps(bundle, sort_keys=True, default=str).encode("utf-8")
    store.put(
        "evidence_items",
        evidence_id,
        {
            "evidence_id": evidence_id,
            "customer_id": bundle.get("customer_id") or "default_customer",
            "project_id": bundle.get("project_id") or "default_project",
            "run_id": bundle.get("run_id") or "",
            "filename": "full-assessment-complexity-evidence.json",
            "content_type": "application/json",
            "size_bytes": len(encoded),
            "source": "github_api_bounded_complexity_analysis",
            "repository": bundle.get("repository") or "",
            "evidence": bundle,
        },
    )
    return bundle


def collect_repository_complexity_evidence(
    context: dict[str, Any],
    *,
    client: GitHubAssessmentClient | None = None,
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    """Collect and persist one deterministic, same-run complexity artifact."""

    active_store = _store(store)
    run_id = str(context.get("run_id") or "").strip()
    repository = str(context.get("repository") or "").strip()
    evidence_id = _evidence_id(run_id, repository)
    existing = active_store.get("evidence_items", evidence_id)
    existing_bundle = existing.get("evidence") if isinstance(existing, dict) and isinstance(existing.get("evidence"), dict) else None
    if existing_bundle:
        reused = dict(existing_bundle)
        reused["idempotent_reuse"] = True
        return reused

    github = client or GitHubAssessmentClient()
    repo_meta, repo_error = github.get_repo(repository)
    if repo_error or not repo_meta:
        bundle = {
            "status": "unavailable",
            "evidence_id": evidence_id,
            "run_id": run_id,
            "repository": repository,
            "customer_id": context.get("customer_id") or "default_customer",
            "project_id": context.get("project_id") or "default_project",
            "source": "github_api_bounded_complexity_analysis",
            "unavailable_data_notes": [_safe_note(repo_error)],
            "idempotent_reuse": False,
            "human_review_required": True,
        }
        return _persist(bundle, active_store)

    profile = fetch_repository_profile(github, repository, repo_meta)
    files = profile.get("files") if isinstance(profile.get("files"), dict) else {}
    measured = collect_complexity_evidence(files)
    bundle = {
        **measured,
        "evidence_id": evidence_id,
        "run_id": run_id,
        "repository": repository,
        "customer_id": context.get("customer_id") or "default_customer",
        "project_id": context.get("project_id") or "default_project",
        "source": "github_api_bounded_complexity_analysis",
        "authorization_scope": context.get("authorization_scope") or "repository assessment only",
        "profiled_file_count": len(files),
        "profile_unavailable_count": len(profile.get("unavailable") or []),
        "idempotent_reuse": False,
        "human_review_required": True,
    }
    notes = list(bundle.get("unavailable_data_notes") or [])
    if profile.get("unavailable"):
        notes.append(
            f"{len(profile.get('unavailable') or [])} repository profile item(s) were unavailable; complexity coverage is limited to readable sampled files."
        )
    bundle["unavailable_data_notes"] = sorted({str(note) for note in notes if str(note).strip()})
    return _persist(bundle, active_store)
