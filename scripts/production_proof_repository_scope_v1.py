"""Repository-bound metadata for controlled public production proof intakes."""
from __future__ import annotations

from urllib.parse import urlsplit


def proof_repository_scope(repository: str) -> dict[str, str]:
    raw = str(repository or "").strip().rstrip("/")
    if not raw:
        raise ValueError("production proof repository is required")
    if "://" not in raw:
        host = raw.split("/", 1)[0].lower()
        raw = "https://" + (raw if "." in host else "github.com/" + raw)
    parsed = urlsplit(raw)
    providers = {"github.com": "GitHub", "gitlab.com": "GitLab",
                 "bitbucket.org": "Bitbucket", "dev.azure.com": "Azure DevOps"}
    host = (parsed.hostname or "").lower()
    parts = parsed.path.strip("/").split("/")
    if (parsed.scheme != "https" or host not in providers
            or parsed.username or parsed.password or parsed.port
            or parsed.query or parsed.fragment or len(parts) < 2
            or any(not part or part in {".", ".."} for part in parts)):
        raise ValueError("unsupported production proof repository locator")
    identity = host + "/" + "/".join(parts).removesuffix(".git")
    return {
        "repository_identity": identity,
        "access_method": f"Public {providers[host]} repository via HTTPS/API — read-only access",
        "authorized_scope": (
            f"{identity} — repository snapshot selected at intake, including source "
            "code, configuration, CI/CD workflows, dependency manifests, documentation, "
            "and repository metadata. Read-only technical and security assessment."
        ),
    }


def validate_report_repository_scope(canonical: dict, acceptance: dict, audit: dict,
                                     pdf_text: str) -> str:
    """Reject stale or cross-repository proof metadata before completion binding."""
    expected = proof_repository_scope(
        acceptance.get("authorized_repository") or acceptance.get("repository") or ""
    )
    identity = canonical.get("identity") or {}
    metadata = canonical.get("engagement_metadata") or {}
    target = expected["repository_identity"]
    for value in (identity.get("repository"), audit.get("repository")):
        if proof_repository_scope(value)["repository_identity"] != target:
            raise ValueError("Completion report repository identity mismatch")
    if identity.get("commit_sha") != acceptance.get("assessed_commit_sha"):
        raise ValueError("Completion report assessed commit mismatch")
    compact = " ".join(pdf_text.split())
    for fields in (identity, metadata):
        scope = str(fields.get("authorized_scope") or "")
        # The controlled proof scope begins with an explicit repository locator.
        scope_target = scope.split(" — ", 1)[0]
        if proof_repository_scope(scope_target)["repository_identity"] != target:
            raise ValueError("Completion report authorized scope repository mismatch")
        access = str(fields.get("access_method") or "")
        if access != expected["access_method"]:
            raise ValueError("Completion report access method provider mismatch")
        if any(" ".join(value.split()) not in compact for value in (scope, access)):
            raise ValueError("Completion report PDF authorization metadata mismatch")
    return target
