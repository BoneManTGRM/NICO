from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol


class PatchSandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileReplacement:
    path: str
    content: str
    expected_sha256: str


@dataclass(frozen=True)
class PatchPlan:
    proposal_id: str
    repository: str
    base_sha: str
    branch_name: str
    commit_message: str
    pull_request_title: str
    pull_request_body: str
    replacements: tuple[FileReplacement, ...]
    approved_paths: tuple[str, ...]


@dataclass(frozen=True)
class PatchResult:
    proposal_id: str
    repository: str
    base_sha: str
    branch_name: str
    changed_paths: tuple[str, ...]
    before_fingerprints: Mapping[str, str]
    after_fingerprints: Mapping[str, str]
    patch_fingerprint: str
    commit_sha: str
    pull_request_url: str
    production_modified: bool = False


class PullRequestGateway(Protocol):
    def create_branch(self, *, repository: str, branch_name: str, base_sha: str) -> None:
        ...

    def replace_files(
        self,
        *,
        repository: str,
        branch_name: str,
        replacements: Mapping[str, str],
        commit_message: str,
    ) -> str:
        ...

    def open_pull_request(
        self,
        *,
        repository: str,
        branch_name: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> str:
        ...


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _safe_relative_path(value: str) -> str:
    token = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(token)
    if not token or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise PatchSandboxError("patch_path_invalid")
    if any(part in {".git", ".github"} for part in path.parts):
        raise PatchSandboxError("patch_protected_path_forbidden")
    return str(path)


def _validate_branch(value: str) -> str:
    token = str(value or "").strip()
    if not token or token.startswith("-") or ".." in token or token.endswith("/"):
        raise PatchSandboxError("patch_branch_invalid")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/.")
    if not set(token).issubset(allowed):
        raise PatchSandboxError("patch_branch_invalid")
    if token in {"main", "master", "production"}:
        raise PatchSandboxError("patch_production_branch_forbidden")
    return token


def validate_patch_plan(plan: PatchPlan) -> tuple[str, ...]:
    if not plan.proposal_id or not plan.repository or not plan.base_sha:
        raise PatchSandboxError("patch_identity_required")
    _validate_branch(plan.branch_name)
    if not plan.commit_message or not plan.pull_request_title or not plan.pull_request_body:
        raise PatchSandboxError("patch_review_metadata_required")
    approved = {_safe_relative_path(item) for item in plan.approved_paths}
    if not approved:
        raise PatchSandboxError("patch_approved_paths_required")
    changed: list[str] = []
    for replacement in plan.replacements:
        path = _safe_relative_path(replacement.path)
        if path not in approved:
            raise PatchSandboxError("patch_path_outside_approval_scope")
        if path in changed:
            raise PatchSandboxError("patch_duplicate_path")
        if not replacement.expected_sha256.startswith("sha256:"):
            raise PatchSandboxError("patch_expected_fingerprint_required")
        changed.append(path)
    if not changed:
        raise PatchSandboxError("patch_replacements_required")
    return tuple(changed)


class LocalPatchSandbox:
    """Applies approved replacements only inside an isolated checked-out workspace."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        if not self.workspace.exists() or not self.workspace.is_dir():
            raise PatchSandboxError("patch_workspace_missing")

    def _target(self, relative: str) -> Path:
        safe = _safe_relative_path(relative)
        target = (self.workspace / safe).resolve()
        try:
            target.relative_to(self.workspace)
        except ValueError as exc:
            raise PatchSandboxError("patch_path_escaped_workspace") from exc
        current = self.workspace
        for part in PurePosixPath(safe).parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise PatchSandboxError("patch_symlink_parent_forbidden")
        if target.is_symlink():
            raise PatchSandboxError("patch_symlink_target_forbidden")
        return target

    def stage(self, plan: PatchPlan) -> tuple[dict[str, str], dict[str, str]]:
        validate_patch_plan(plan)
        before: dict[str, str] = {}
        after: dict[str, str] = {}
        for replacement in plan.replacements:
            path = _safe_relative_path(replacement.path)
            target = self._target(path)
            existing = target.read_bytes() if target.exists() else b""
            observed = _sha256_bytes(existing)
            if observed != replacement.expected_sha256:
                raise PatchSandboxError("patch_source_fingerprint_mismatch")
            encoded = replacement.content.encode("utf-8")
            before[path] = observed
            after[path] = _sha256_bytes(encoded)
        for replacement in plan.replacements:
            path = _safe_relative_path(replacement.path)
            target = self._target(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.nico-tmp-{os.getpid()}")
            temporary.write_text(replacement.content, encoding="utf-8")
            temporary.replace(target)
        return before, after


def submit_patch_plan(
    plan: PatchPlan,
    *,
    gateway: PullRequestGateway,
    base_branch: str = "main",
) -> PatchResult:
    paths = validate_patch_plan(plan)
    if base_branch != "main":
        raise PatchSandboxError("patch_base_branch_must_be_main")
    replacements = {item.path: item.content for item in plan.replacements}
    before = {item.path: item.expected_sha256 for item in plan.replacements}
    after = {path: _sha256_bytes(content.encode("utf-8")) for path, content in replacements.items()}
    patch_fingerprint = _sha256_bytes(
        "\n".join(
            f"{path}|{before[path]}|{after[path]}"
            for path in sorted(paths)
        ).encode("utf-8")
    )
    gateway.create_branch(
        repository=plan.repository,
        branch_name=plan.branch_name,
        base_sha=plan.base_sha,
    )
    commit_sha = gateway.replace_files(
        repository=plan.repository,
        branch_name=plan.branch_name,
        replacements=replacements,
        commit_message=plan.commit_message,
    )
    pull_request_url = gateway.open_pull_request(
        repository=plan.repository,
        branch_name=plan.branch_name,
        base_branch=base_branch,
        title=plan.pull_request_title,
        body=plan.pull_request_body,
    )
    if not commit_sha or not pull_request_url:
        raise PatchSandboxError("patch_gateway_result_incomplete")
    return PatchResult(
        proposal_id=plan.proposal_id,
        repository=plan.repository,
        base_sha=plan.base_sha,
        branch_name=plan.branch_name,
        changed_paths=paths,
        before_fingerprints=before,
        after_fingerprints=after,
        patch_fingerprint=patch_fingerprint,
        commit_sha=commit_sha,
        pull_request_url=pull_request_url,
        production_modified=False,
    )


__all__ = [
    "FileReplacement",
    "LocalPatchSandbox",
    "PatchPlan",
    "PatchResult",
    "PatchSandboxError",
    "PullRequestGateway",
    "submit_patch_plan",
    "validate_patch_plan",
]
