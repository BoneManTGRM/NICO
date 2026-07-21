from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from nico.monitor_patch_sandbox import (
    FileReplacement,
    LocalPatchSandbox,
    PatchPlan,
    PatchSandboxError,
    submit_patch_plan,
    validate_patch_plan,
)


def _digest(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _plan(*, path: str = "nico/example.py", expected: str = "sha256:old") -> PatchPlan:
    return PatchPlan(
        proposal_id="proposal-1",
        repository="BoneManTGRM/NICO",
        base_sha="a" * 40,
        branch_name="nico-remediation/proposal-1",
        commit_message="Apply approved bounded repair",
        pull_request_title="Approved remediation proposal-1",
        pull_request_body="Exact-SHA, path-scoped remediation requiring review.",
        replacements=(FileReplacement(path=path, content="print('new')\n", expected_sha256=expected),),
        approved_paths=("nico/example.py",),
    )


def test_local_sandbox_applies_only_exact_fingerprint_approved_path(tmp_path: Path) -> None:
    target = tmp_path / "nico" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('old')\n", encoding="utf-8")
    expected = _digest(target.read_bytes())

    before, after = LocalPatchSandbox(tmp_path).stage(_plan(expected=expected))

    assert before["nico/example.py"] == expected
    assert after["nico/example.py"] == _digest(b"print('new')\n")
    assert target.read_text(encoding="utf-8") == "print('new')\n"


def test_sandbox_rejects_path_traversal_protected_paths_and_scope_escape(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    with pytest.raises(PatchSandboxError, match="patch_path_invalid"):
        validate_patch_plan(_plan(path="../outside.py"))
    with pytest.raises(PatchSandboxError, match="patch_protected_path_forbidden"):
        validate_patch_plan(_plan(path=".github/workflows/release.yml"))

    out_of_scope = PatchPlan(
        **{
            **_plan(path="other.py").__dict__,
            "approved_paths": ("nico/example.py",),
        }
    )
    with pytest.raises(PatchSandboxError, match="patch_path_outside_approval_scope"):
        validate_patch_plan(out_of_scope)


def test_sandbox_rejects_source_drift_and_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "nico" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("changed outside approval\n", encoding="utf-8")
    with pytest.raises(PatchSandboxError, match="patch_source_fingerprint_mismatch"):
        LocalPatchSandbox(tmp_path).stage(_plan(expected="sha256:stale"))

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)
    plan = PatchPlan(
        **{
            **_plan(path="linked/example.py", expected=_digest(b"")).__dict__,
            "approved_paths": ("linked/example.py",),
        }
    )
    with pytest.raises(PatchSandboxError, match="patch_symlink_parent_forbidden"):
        LocalPatchSandbox(tmp_path).stage(plan)


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    def create_branch(self, **kwargs):
        self.calls.append(("branch", kwargs))

    def replace_files(self, **kwargs):
        self.calls.append(("replace", kwargs))
        return "b" * 40

    def open_pull_request(self, **kwargs):
        self.calls.append(("pr", kwargs))
        return "https://github.com/BoneManTGRM/NICO/pull/999"


def test_submission_creates_reviewable_pr_without_modifying_production() -> None:
    gateway = FakeGateway()
    result = submit_patch_plan(_plan(), gateway=gateway)

    assert [name for name, _ in gateway.calls] == ["branch", "replace", "pr"]
    assert gateway.calls[0][1]["base_sha"] == "a" * 40
    assert gateway.calls[2][1]["base_branch"] == "main"
    assert result.commit_sha == "b" * 40
    assert result.pull_request_url.endswith("/999")
    assert result.production_modified is False
    assert result.patch_fingerprint.startswith("sha256:")


def test_submission_forbids_direct_production_branch() -> None:
    plan = PatchPlan(**{**_plan().__dict__, "branch_name": "main"})
    with pytest.raises(PatchSandboxError, match="patch_production_branch_forbidden"):
        submit_patch_plan(plan, gateway=FakeGateway())
