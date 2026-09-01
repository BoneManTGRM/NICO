from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v3_proof_binds_distinct_spanish_terminal_fields() -> None:
    source = (
        ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"
    ).read_text(encoding="utf-8")

    assert 'SPANISH_TERMINAL_PHASE = "Se requiere revisión experta"' in source
    assert 'SPANISH_TERMINAL_REVIEW = "Revisión interna requerida"' in source
    assert 'SPANISH_TERMINAL_REPORT = "Completa"' in source
    assert 'terminal.get("phase") == SPANISH_TERMINAL_PHASE' in source
    assert 'terminal.get("review") == SPANISH_TERMINAL_REVIEW' in source
    assert 'terminal.get("report") == SPANISH_TERMINAL_REPORT' in source
    assert "LOCALIZED_PDF_CONNECT_TIMEOUT_SECONDS = 300.0" in source
    assert "LOCALIZED_PDF_READ_TIMEOUT_SECONDS = 300.0" in source
    assert "with httpx.Client(" in source
    assert "response = client.get(" in source
    assert "response = page.request.get(" not in source[
        source.index("def _fetch_localized_pdf(") : source.index(
            "def _verify_localized_spanish_terminal_artifacts("
        )
    ]
    assert "return telemetry.main(argv)" in source


def test_durable_engagement_read_waits_for_intake_visibility(tmp_path: Path) -> None:
    playwright = tmp_path / "stubs" / "playwright"
    playwright.mkdir(parents=True)
    (playwright / "__init__.py").write_text("", encoding="utf-8")
    (playwright / "sync_api.py").write_text(
        "class Browser: pass\n"
        "class Page: pass\n"
        "def sync_playwright(): raise AssertionError('unit probe must not start a browser')\n",
        encoding="utf-8",
    )
    script = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"
    probe = f"""
import runpy
import sys
from pathlib import Path

repository_root = Path({str(ROOT)!r})
sys.path[:] = [
    {str(script.parent)!r},
    *(entry for entry in sys.path if Path(entry or ".").resolve() != repository_root),
]
sys.meta_path[:] = [
    finder
    for finder in sys.meta_path
    if "editable" not in type(finder).__module__.casefold()
]
module = runpy.run_path({str(script)!r}, run_name="nico_visibility_retry_unit_probe")
metadata = dict(
    module["_expected_engagement_metadata"](),
    repository_inference_prohibited=True,
    directly_scored=False,
)

class Response:
    def __init__(self, status, payload=None):
        self.status = status
        self.ok = 200 <= status < 300
        self._payload = payload

    def json(self):
        return self._payload

class Requests:
    def __init__(self):
        self.responses = [
            Response(404),
            Response(
                200,
                dict(
                    intake_reserved=True,
                    operation="intake_pending",
                    terminal=False,
                ),
            ),
            Response(
                200,
                dict(
                    run_id="comprun_visibility",
                    commit_sha="a" * 40,
                    engagement_metadata=metadata,
                    record=dict(
                        identity=dict(commit_sha="a" * 40),
                        engagement_metadata=metadata,
                    ),
                ),
            ),
        ]
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

class Page:
    def __init__(self):
        self.request = Requests()
        self.waits = []

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)

page = Page()
result = module["_fetch_and_verify_durable_engagement"](
    page,
    frontend_origin="https://app.nicoaudit.com",
    run_id="comprun_visibility",
    boundary="unit_test",
)
assert result["visibility_read_attempt_count"] == 3
assert result["visibility_not_found_read_count"] == 1
assert result["visibility_pending_read_count"] == 1
assert result["snapshot_commit_sha"] == "a" * 40
assert len(page.request.calls) == 3
assert page.waits == [module["ENGAGEMENT_VISIBILITY_RETRY_MILLISECONDS"]] * 2

drift = Page()
drift.request.responses = [
    Response(
        200,
        dict(
            run_id="comprun_visibility",
            commit_sha="a" * 40,
            engagement_metadata=metadata,
            record=dict(
                identity=dict(commit_sha="b" * 40),
                engagement_metadata=metadata,
            ),
        ),
    )
]
try:
    module["_fetch_and_verify_durable_engagement"](
        drift,
        frontend_origin="https://app.nicoaudit.com",
        run_id="comprun_visibility",
        boundary="unit_test_snapshot_drift",
    )
except AssertionError as exc:
    assert "record_snapshot_commit_sha" in str(exc)
else:
    raise AssertionError("cross-projection snapshot drift was accepted")

blocked = Page()
blocked.request.responses = [Response(403)]
try:
    module["_fetch_and_verify_durable_engagement"](
        blocked,
        frontend_origin="https://app.nicoaudit.com",
        run_id="comprun_visibility",
        boundary="unit_test_permanent_failure",
    )
except AssertionError as exc:
    assert "returned HTTP 403" in str(exc)
else:
    raise AssertionError("permanent HTTP failure was retried or accepted")
assert len(blocked.request.calls) == 1
assert blocked.waits == []
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path / "stubs")
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_release_sha_and_assessed_snapshot_sha_remain_distinct() -> None:
    source_path = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"
    source = source_path.read_text(encoding="utf-8")
    recovery = (
        ROOT / "scripts" / "spanish_comprehensive_existing_run_recovery_v1.py"
    ).read_text(encoding="utf-8")

    assert 'initial_engagement["snapshot_commit_sha"]' in source
    assert 'expected_commit_sha=initial_engagement["snapshot_commit_sha"]' in source
    assert 'snapshot_commit_sha = initial_view["commit_sha"]' in recovery
    assert '"expected_sha": release_sha' in recovery
    assert '"assessed_commit_sha": snapshot_commit_sha' in recovery
    assert "expected_commit_sha=snapshot_commit_sha" in recovery


def test_exclusion_probe_verifies_rendered_view_after_field_unmounting() -> None:
    source = (
        ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"
    ).read_text(encoding="utf-8")

    helper_start = source.index("def _verify_excluded_engagement_ui(")
    helper_end = source.index(
        "def _commercial_spanish_run_proof(",
        helper_start,
    )
    helper = source[helper_start:helper_end]
    commercial = source[helper_end:]
    strategic_evidence = (
        ROOT / "apps/web/app/assessment/strategicEvidence.ts"
    ).read_text(encoding="utf-8")

    assert (
        'if (value.excluded && value.exclusion_rationale.trim()) return "excluded";'
        in strategic_evidence
    )
    assert '"Justificación de exclusión"' in helper
    assert 'wait_for(state="visible", timeout=30_000)' in helper
    assert 'assert exclusion_rationale.input_value() == ""' in helper
    assert 'exclusion_rationale.fill(PROOF_EXCLUSION_RATIONALE)' in helper
    assert "page.wait_for_function(" in helper
    assert "arg={" in helper
    assert 'root.querySelectorAll(\'label\')' in helper
    assert '"expectedValue": PROOF_EXCLUSION_RATIONALE' in helper
    assert "label?.querySelector('textarea')?.value" in helper
    assert '"exclusion_rationale_supplied": True' in helper
    assert helper.index(
        "exclusion_rationale.fill(PROOF_EXCLUSION_RATIONALE)"
    ) < helper.index('"Excluido con justificación"')
    assert '"expected": "unmounted_after_module_exclusion"' in helper
    assert '"excluded_field_controls_unmounted": True' in helper
    assert 'assert count == 0' in helper
    assert 'get_attribute("data-engagement-state")' not in commercial
    assert '"exclusion_ui": exclusion_ui' in commercial


def test_release_browser_matrix_reuses_one_public_gitlab_snapshot() -> None:
    fixture = "https://gitlab.com/gitlab-org/gitlab-test"
    workflows = [
        ROOT / ".github/workflows/spanish-comprehensive-production-proof.yml",
        ROOT / ".github/workflows/two-service-production-acceptance.yml",
        ROOT / ".github/workflows/mobile-restart-production-proof.yml",
        ROOT / ".github/workflows/ios-webkit-paint-proof.yml",
    ]
    sources = [path.read_text(encoding="utf-8") for path in workflows]

    assert all(
        f"NICO_PRODUCTION_SMOKE_REPOSITORY: {fixture}" in source
        for source in sources
    )
    assert all("NICO_PRODUCTION_SMOKE_REPOSITORY" in source for source in sources)
    assert (
        f'test "${{NICO_PRODUCTION_SMOKE_REPOSITORY}}" = "{fixture}"'
        in sources[0]
    )
    assert (
        f'test "${{NICO_PRODUCTION_SMOKE_REPOSITORY}}" = "{fixture}"'
        in sources[1]
    )
    assert "Spanish Comprehensive Production Proof" in sources[1]
    assert "Spanish Comprehensive Production Proof" in sources[2]
    assert "Spanish Comprehensive Production Proof" in sources[3]


def test_production_workflow_uses_v3_and_exact_terminal_assertions() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "spanish-comprehensive-production-proof.yml"
    ).read_text(encoding="utf-8")

    assert "python scripts/spanish_comprehensive_live_acceptance_v3.py" in workflow
    assert 'payload["terminal"]["phase"] == "Se requiere revisión experta"' in workflow
    assert 'payload["terminal"]["review"] == "Revisión interna requerida"' in workflow
    assert 'payload["terminal"]["report"] == "Completa"' in workflow


def test_v3_exclusion_fixture_keeps_values_empty_and_states_explicit(
    tmp_path: Path,
) -> None:
    playwright = tmp_path / "stubs" / "playwright"
    playwright.mkdir(parents=True)
    (playwright / "__init__.py").write_text("", encoding="utf-8")
    (playwright / "sync_api.py").write_text(
        "class Browser: pass\n"
        "class Page: pass\n"
        "def sync_playwright(): raise AssertionError('unit probe must not start a browser')\n",
        encoding="utf-8",
    )
    script = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"
    probe = f"""
import os
import runpy
import sys
from pathlib import Path

repository_root = Path({str(ROOT)!r})
sys.path[:] = [
    {str(script.parent)!r},
    *(
        entry
        for entry in sys.path
        if Path(entry or ".").resolve() != repository_root
    ),
]
sys.meta_path[:] = [
    finder
    for finder in sys.meta_path
    if "editable" not in type(finder).__module__.casefold()
]
os.environ["NICO_SPANISH_PROOF_ENGAGEMENT_FIXTURE"] = "excluded"
module = runpy.run_path({str(script)!r}, run_name="nico_exclusion_fixture_unit_probe")
assert module["_expected_engagement_metadata"]() == {{
    "client_name": "Cody Jenkins",
    "project_name": "NICO Audit",
    "primary_technical_contact": "",
    "access_method": "",
    "authorized_scope": "",
}}
assert module["_expected_client_summary_values"]("en") == (
    "Cody Jenkins", "NICO Audit", "Excluded from scope",
    "Excluded from scope", "Excluded from scope",
)
assert module["_expected_client_summary_values"]("es-MX") == (
    "Cody Jenkins", "NICO Audit", "Excluido del alcance",
    "Excluido del alcance", "Excluido del alcance",
)
fields = module["EXCLUDED_ENGAGEMENT_FIELDS"]
valid = {{
    "engagement_field_states": {{
        field: {{
            "state": "excluded_from_scope",
            "value": None,
            "source": "user_action",
        }}
        for field in fields
    }}
}}
module["_assert_excluded_field_states"](valid, boundary="unit_test")
invalid = {{
    "engagement_field_states": {{
        field: {{"state": "not_supplied", "value": None, "source": "intake"}}
        for field in fields
    }}
}}
try:
    module["_assert_excluded_field_states"](invalid, boundary="unit_test")
except AssertionError:
    pass
else:
    raise AssertionError("not_supplied substitution was accepted")
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path / "stubs")
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_v3_entrypoint_imports_nico_when_invoked_by_path(tmp_path: Path) -> None:
    playwright = tmp_path / "stubs" / "playwright"
    playwright.mkdir(parents=True)
    (playwright / "__init__.py").write_text("", encoding="utf-8")
    (playwright / "sync_api.py").write_text(
        "class Browser: pass\n"
        "class Page: pass\n"
        "def sync_playwright(): raise AssertionError('preflight must not start a browser')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path / "stubs")
    script = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"
    import_only = f"""
import runpy
import sys
from pathlib import Path

repository_root = Path({str(ROOT)!r})
sys.path[:] = [
    {str(script.parent)!r},
    *(
        entry
        for entry in sys.path
        if Path(entry or ".").resolve() != repository_root
    ),
]
sys.meta_path[:] = [
    finder
    for finder in sys.meta_path
    if "editable" not in type(finder).__module__.casefold()
]
runpy.run_path(
    {str(script)!r},
    run_name="nico_spanish_proof_import_preflight",
)
"""
    completed = subprocess.run(
        [sys.executable, "-c", import_only],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_production_workflow_preflights_entrypoint_before_assessment() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "spanish-comprehensive-production-proof.yml"
    ).read_text(encoding="utf-8")

    install = workflow.index("Install pinned browser proof dependencies")
    preflight = workflow.index("Verify Spanish proof entrypoint before assessment")
    assessment = workflow.index("Run fresh Spanish Comprehensive final-report proof")
    assert install < preflight < assessment
    install_block = workflow[install:preflight]
    assert '. "playwright==1.61.0" "pypdf==6.15.0"' in install_block
    assert 'run_name="nico_spanish_proof_import_preflight"' in workflow
