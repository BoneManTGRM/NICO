from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from triage662_core import common_record, findings, fingerprint, repo_path, scope, stable_id


def git_metadata(item: dict[str, Any]) -> dict[str, Any]:
    return (((item.get("SourceMetadata") or {}).get("Data") or {}).get("Git") or {})


def secret_record(run: dict[str, Any], sha: str, *, scanner: str, rule: str, path: str,
                  line: int | None, commit: str, verified: bool | None) -> dict[str, Any]:
    is_test = scope(path) == "test" and verified is not True
    row = common_record(
        candidate_id=stable_id("NICO-SECRET", sha, scanner, rule, path, line, commit),
        cluster_id=stable_id("NICO-CLUSTER-SECRET", scanner, rule, scope(path)),
        category="secret", scanner=scanner, rule=rule,
        title="Potential secret-history candidate; credential material omitted.",
        path=path, line=line, severity="unknown",
        confidence="high" if scanner == "gitleaks" else "medium",
        proposed="test_fixture_confirmation_required" if is_test else "secret_exposure_review_required",
        rationale=("The observation is located in test source and is not scanner-verified. It must not be represented as "
                   "production exposure without human confirmation; raw credential material is omitted.") if is_test else
                  ("A secret scanner reported an exact-history observation. Verification, rotation status, and production "
                   "relevance require authorized human review; raw credential material is omitted."),
        sha=sha, evidence_fingerprint=fingerprint(run, scanner),
    )
    row.update({
        "history_commit": commit,
        "verified": verified,
        "secret_material_omitted": True,  # nosec B105 - redaction metadata flag, not a credential
    })
    return row


def secret_candidates(run: dict[str, Any], sha: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output, excluded = [], []
    for item in findings(run, "gitleaks"):
        output.append(secret_record(
            run, sha, scanner="gitleaks", rule=str(item.get("RuleID") or "gitleaks"),
            path=repo_path(item.get("File")), line=int(item.get("StartLine") or 0) or None,
            commit=str(item.get("Commit") or ""), verified=None,
        ))

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in findings(run, "trufflehog"):
        git = git_metadata(item)
        key = (str(item.get("DetectorName") or "trufflehog"), repo_path(git.get("file")),
               int(git.get("line") or 0) or None, str(git.get("commit") or ""),
               bool(item.get("Verified") or False))
        grouped[key].append(item)

    for key in sorted(grouped, key=lambda value: tuple(str(item) for item in value)):
        detector, path, line, commit, verified = key
        rows = grouped[key]
        raw_hashes = {hashlib.sha256(str(item.get("RawV2") or item.get("Raw") or "").encode()).hexdigest() for item in rows}
        if len(raw_hashes) > 1:
            raise ValueError(f"Multiple distinct secret values share one safe metadata location: {path}:{line}")
        for index in range(1, len(rows)):
            excluded.append({
                "exclusion_id": stable_id("NICO-EXCLUDED-DUPLICATE", sha, detector, path, line, commit, index),
                "scanner": "trufflehog", "category": "secret",
                "reason": "exact_duplicate_scanner_observation", "path": path, "line": line,
                "history_commit": commit, "canonical_observation_retained": True,
                "secret_material_omitted": True,  # nosec B105 - redaction metadata flag, not a credential
            })
        if path.casefold() == ".env.example" and verified is False:
            excluded.append({
                "exclusion_id": stable_id("NICO-EXCLUDED-EXAMPLE", sha, detector, path, line, commit),
                "scanner": "trufflehog", "category": "secret",
                "reason": "unverified_example_template_observation", "path": path, "line": line,
                "history_commit": commit, "canonical_observation_retained": False,
                "secret_material_omitted": True,  # nosec B105 - redaction metadata flag, not a credential
            })
            continue
        output.append(secret_record(run, sha, scanner="trufflehog", rule=detector, path=path,
                                    line=line, commit=commit, verified=verified))
    return output, excluded
