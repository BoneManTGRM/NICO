from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from nico.exact_commit_binding import (
    EXACT_COMMIT_BINDING_VERSION,
    _bind_result,
    expected_commit_sha,
)
from nico.repository_snapshot import _expected_commit_sha


ROOT = Path(__file__).resolve().parents[1]
V3_SCRIPT = ROOT / "scripts" / "two_service_live_acceptance_v3.py"
TRANSPORT = ROOT / "apps" / "web" / "app" / "AssessmentExactCommitTransport.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
BOOTSTRAP = ROOT / "nico" / "api" / "terminal_authority_bootstrap.py"


def test_expected_commit_marker_survives_typed_express_request_contract() -> None:
    sha = "a" * 40
    payload = {
        "authorized_by": f"public_assessment_requester;expected_commit_sha={sha}",
    }

    assert expected_commit_sha(payload) == sha
    assert _expected_commit_sha(payload) == (sha, "authorized_request_marker")


def test_verified_commit_replaces_conflicting_derived_identity_but_retains_conflict() -> None:
    canonical = "b" * 40
    stale = "c" * 40
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": stale,
        "scanner_worker_auto_ran": False,
    }

    output = _bind_result(
        result,
        repository="BoneManTGRM/NICO",
        commit_sha=canonical,
        requested_sha=canonical,
        scanner_checkout_sha="",
    )

    assert output["commit_sha"] == canonical
    assert output["repository_snapshot"]["commit_sha"] == canonical
    assert output["exact_commit_binding"]["version"] == EXACT_COMMIT_BINDING_VERSION
    assert output["exact_commit_binding"]["preexisting_commit_conflict_removed"] is True
    assert output["commit_identity_conflict"]["observed"] == stale
    assert output["commit_identity_conflict"]["canonical"] == canonical
    assert output["human_review_required"] if "human_review_required" in output else True


def test_auto_run_scanner_must_verify_the_same_exact_commit() -> None:
    canonical = "d" * 40
    output = _bind_result(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "scanner_worker_auto_ran": True,
        },
        repository="BoneManTGRM/NICO",
        commit_sha=canonical,
        requested_sha=canonical,
        scanner_checkout_sha="e" * 40,
    )

    assert output["status"] == "blocked"
    assert output["code"] == "exact_scanner_checkout_unverified"
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False


def _v3_module():
    for name, path in (
        ("two_service_live_acceptance", ROOT / "scripts" / "two_service_live_acceptance.py"),
        ("two_service_live_acceptance_v2", ROOT / "scripts" / "two_service_live_acceptance_v2.py"),
    ):
        if name in sys.modules:
            continue
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    spec = importlib.util.spec_from_file_location("two_service_live_acceptance_v3_exact_test", V3_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_navigation_carries_the_exact_release_sha() -> None:
    module = _v3_module()
    seen: list[str] = []

    class Page:
        def goto(self, url: str, *args, **kwargs):
            seen.append(url)
            return "ok"

    sha = "f" * 40
    page = module._ExpectedCommitPage(Page(), sha)
    assert page.goto("https://app.nicoaudit.com/assessment?tier=express#assessment") == "ok"
    assert seen == [
        f"https://app.nicoaudit.com/assessment?tier=express&expected_commit_sha={sha}#assessment"
    ]


def test_frontend_and_production_bootstrap_install_exact_commit_contract() -> None:
    transport = TRANSPORT.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

    assert "expected_commit_sha" in transport
    assert "authorized_by" in transport
    assert "AssessmentExactCommitTransport" in layout
    assert bootstrap.index("install_exact_commit_binding()") < bootstrap.index("install_express_terminal_authority()")
    assert "repository_files_bound_to_exact_commit" in bootstrap
    assert "scanner_bound_to_exact_commit" in bootstrap
