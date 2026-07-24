from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from nico.exact_commit_binding import (
    install_exact_commit_binding,
    reconcile_exact_commit,
)


ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentExactCommitTransport.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
BOOTSTRAP = ROOT / "nico" / "api" / "terminal_authority_bootstrap.py"
V3_SCRIPT = ROOT / "scripts" / "two_service_live_acceptance_v3.py"


def test_exact_commit_binding_installation_contract_is_fail_closed() -> None:
    output = install_exact_commit_binding()

    assert output["status"] in {"installed", "already_installed"}
    assert output["repository_files_bound_to_exact_commit"] is True
    assert output["scanner_bound_to_exact_commit"] is True
    assert output["exact_commit_required"] is True
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False


def test_exact_commit_reconciliation_accepts_matching_repository_and_scanner_sha() -> None:
    commit = "d" * 40

    output = reconcile_exact_commit(
        expected_commit_sha=commit,
        repository_commit_sha=commit,
        scanner_checkout_sha=commit,
    )

    assert output["status"] == "verified"
    assert output["commit_sha"] == commit
    assert output["repository_files_bound_to_exact_commit"] is True
    assert output["scanner_bound_to_exact_commit"] is True
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False


def test_exact_commit_reconciliation_blocks_repository_mismatch() -> None:
    output = reconcile_exact_commit(
        expected_commit_sha="d" * 40,
        repository_commit_sha="e" * 40,
        scanner_checkout_sha="d" * 40,
    )

    assert output["status"] == "blocked"
    assert output["code"] == "exact_repository_commit_mismatch"
    assert output["human_review_required"] is True
    assert output["client_delivery_allowed"] is False


def test_exact_commit_reconciliation_blocks_unverified_scanner_checkout() -> None:
    output = reconcile_exact_commit(
        expected_commit_sha="d" * 40,
        repository_commit_sha="d" * 40,
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


def test_acceptance_navigation_carries_exact_release_sha_and_canonical_tier() -> None:
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
        f"https://app.nicoaudit.com/assessment?tier=comprehensive&expected_commit_sha={sha}#assessment"
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
