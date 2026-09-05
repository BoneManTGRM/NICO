"""A configured label must never overrule the actual deployed source identity."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from nico.comprehensive_release_provenance_v1 import comprehensive_release_provenance


@pytest.fixture(autouse=True)
def isolated_release_environment(monkeypatch):
    for name in ("NICO_RELEASE_COMMIT_SHA", "RAILWAY_GIT_COMMIT_SHA", "GITHUB_SHA",
                 "NICO_FRONTEND_BUILD_COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA"):
        monkeypatch.delenv(name, raising=False)


def test_native_backend_identity_survives_a_stale_configured_release(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "b" * 40)
    actual = comprehensive_release_provenance()
    assert actual["backend_build_commit"] == "a" * 40
    assert actual["deployment_identity_established"] is False
    assert actual.get("deployment_identity_conflict") is True


@pytest.mark.parametrize("configured", [None, "a" * 40])
def test_matching_or_absent_override_keeps_native_identity_valid(monkeypatch, configured):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "a" * 40)
    if configured is not None:
        monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", configured)
    actual = comprehensive_release_provenance()
    assert actual["backend_build_commit"] == "a" * 40
    assert actual["deployment_identity_established"] is True
    assert actual.get("deployment_identity_conflict", False) is False


def test_invalid_native_identity_cannot_fall_back_to_a_configured_label(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "invalid-native")
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "b" * 40)
    actual = comprehensive_release_provenance()
    assert actual["backend_build_commit"] == "unavailable"
    assert actual["deployment_identity_established"] is False


def test_non_railway_explicit_identity_remains_supported(monkeypatch):
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "b" * 40)
    actual = comprehensive_release_provenance()
    assert actual["backend_build_commit"] == "b" * 40
    assert actual["deployment_identity_established"] is True


def test_specialist_readiness_requires_consistent_release_identities():
    # Exercise the actual installed readiness function in an isolated process.
    script = r'''
from nico.api import specialist_ship_ready_bootstrap as b
b._configured_credentials = lambda: {'admin':'test-admin', 'operator':'test-operator', 'legacy_operator':'', 'session_signing':'test-signing'}
b._positive_authentication_self_test = lambda _: {'operator_credential_self_test':True, 'session_round_trip_self_test':True, 'positive_authentication_verified_server_side':True}
b.SPECIALIST_ACCESS = {'installed':True, 'session_signing_configured':True, 'all_assessment_routes_protected':True, 'all_report_routes_protected':True, 'rate_limiting':True}
b.REVIEW_SESSION_BRIDGE = {'installed':True}
b.APPROVED_LIFECYCLE_CONSISTENCY = {'installed':True, 'cross_format_fail_closed':True}
b.app.state.nico_comprehensive_production_runtime = {'status':'ready', 'survives_container_replacement_verified':True, 'human_review_required':True, 'client_delivery_allowed':False}
release = {'deployment_identity_established':True, 'frontend_identity_established':True, 'backend_build_commit':'a'*40, 'frontend_build_commit':'a'*40}
b.comprehensive_release_provenance = lambda: release
assert b.specialist_readiness()['status'] == 'ready'
release['frontend_build_commit'] = 'b'*40
result = b.specialist_readiness()
assert result['status'] == 'blocked', 'mismatched releases were reported ready'
assert result['release_identity_complete'] is False
release['frontend_build_commit'] = 'a'*40
release['deployment_identity_conflict'] = True
assert b.specialist_readiness()['status'] == 'blocked'
release.pop('deployment_identity_conflict')
for bad in ('unavailable', '', 'short'):
    release['backend_build_commit'] = release['frontend_build_commit'] = bad
    assert b.specialist_readiness()['status'] == 'blocked'
assert result['client_delivery_allowed'] is False
assert result['human_review_required'] is True
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=35, check=False)
    assert result.returncode == 0, result.stderr[-2500:]
