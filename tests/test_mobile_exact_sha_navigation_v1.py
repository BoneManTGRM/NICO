from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path("scripts/mobile_exact_sha_navigation_v1.py")
SPEC = importlib.util.spec_from_file_location("mobile_exact_sha_navigation_v1", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_exact_sha_is_added_to_assessment_navigation_only() -> None:
    sha = "a" * 40
    bound = module.bind_expected_sha(
        "https://app.nicoaudit.com/assessment?tier=comprehensive&mobile_restart_probe=123#assessment",
        sha,
    )
    assert "expected_commit_sha=" + sha in bound
    assert "tier=comprehensive" in bound
    assert "mobile_restart_probe=123" in bound
    assert bound.endswith("#assessment")
    assert module.bind_expected_sha("https://app.nicoaudit.com/api/release", sha) == "https://app.nicoaudit.com/api/release"


def test_spanish_assessment_navigation_is_bound() -> None:
    sha = "b" * 40
    bound = module.bind_expected_sha("https://app.nicoaudit.com/es/assessment?tier=comprehensive", sha)
    assert "expected_commit_sha=" + sha in bound


def test_conflicting_or_invalid_sha_fails_closed() -> None:
    sha = "c" * 40
    other = "d" * 40
    try:
        module.bind_expected_sha(
            f"https://app.nicoaudit.com/assessment?expected_commit_sha={other}",
            sha,
        )
    except ValueError as exc:
        assert str(exc) == "expected_commit_sha_navigation_conflict"
    else:
        raise AssertionError("conflicting exact SHA did not fail closed")

    try:
        module.bind_expected_sha("https://app.nicoaudit.com/assessment", "not-a-sha")
    except ValueError as exc:
        assert str(exc) == "expected_commit_sha_must_be_40_hex"
    else:
        raise AssertionError("invalid exact SHA did not fail closed")


def test_mobile_and_webkit_wrappers_install_exact_sha_binding() -> None:
    mobile = Path("scripts/mobile_restart_live_acceptance_v5.py").read_text(encoding="utf-8")
    webkit = Path("scripts/mobile_restart_live_acceptance_v6.py").read_text(encoding="utf-8")
    for source in (mobile, webkit):
        assert 'handoff = recovery.load_source_proof(' in source
        assert 'install_exact_sha_navigation(single_dispatch, handoff["assessed_commit_sha"])' in source
        assert "args = recovery.parse_args(argv)" in source


def test_installer_rewrites_page_goto_without_changing_delegate_contract() -> None:
    calls: list[str] = []

    class FakePage:
        def goto(self, url: str, **kwargs):
            calls.append(url)
            return kwargs

    fake_module = SimpleNamespace(_SingleDispatchPage=FakePage)
    sha = "e" * 40
    result = module.install_exact_sha_navigation(fake_module, sha)
    page = FakePage()
    page.goto("https://app.nicoaudit.com/assessment?tier=comprehensive")
    assert calls and "expected_commit_sha=" + sha in calls[-1]
    assert result["assessment_navigation_bound"] is True
