"""Workflow expressions must remain data, not embedded shell source.

Offline checks only; no workflow, database or remote action is executed.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINDINGS = [('.github/workflows/branch-cleanup-issue-control.yml',
  'Generate a fresh branch inventory',
  {'NICO_BOUND_GITHUB_EVENT_REPOSITORY_DEFAULT_BRANCH': '${{ '
                                                        'github.event.repository.default_branch '
                                                        '}}'}),
 ('.github/workflows/branch-cleanup.yml',
  'Generate a fresh read-only inventory',
  {'NICO_BOUND_GITHUB_EVENT_REPOSITORY_DEFAULT_BRANCH': '${{ '
                                                        'github.event.repository.default_branch '
                                                        '}}'}),
 ('.github/workflows/branch-inventory.yml',
  'Generate evidence-backed classifications',
  {'NICO_BOUND_GITHUB_EVENT_REPOSITORY_DEFAULT_BRANCH': '${{ '
                                                        'github.event.repository.default_branch '
                                                        '}}'}),
 ('.github/workflows/ios-webkit-paint-proof.yml',
  'Verify synthetic reviewer lexical binding in hosted WebKit',
  {'NICO_BOUND_GITHUB_EVENT_PULL_REQUEST_HEAD_SHA': '${{ github.event.pull_request.head.sha }}',
   'NICO_BOUND_GITHUB_SHA': '${{ github.sha }}'}),
 ('.github/workflows/phase1-completion-bound-report.yml',
  'Extend the same Comprehensive report with Phase 3 and Phase 4 Engineering closure',
  {'NICO_BOUND_STEPS_CURRENT_HEAD_OUTPUTS_GREEN_WATCH_RUN_ID': '${{ '
                                                               'steps.current_head.outputs.green_watch_run_id '
                                                               '}}',
   'NICO_BOUND_STEPS_CURRENT_HEAD_OUTPUTS_SPANISH_RUN_ID': '${{ '
                                                           'steps.current_head.outputs.spanish_run_id '
                                                           '}}'}),
 ('.github/workflows/phase1-completion-bound-report.yml',
  'Bind Phase 1 and Phase 2 completion truth into the existing Comprehensive report',
  {'NICO_BOUND_GITHUB_EVENT_WORKFLOW_RUN_UPDATED_AT': '${{ github.event.workflow_run.updated_at }}',
   'NICO_BOUND_STEPS_CURRENT_HEAD_OUTPUTS_ARTIFACT_DIGEST': '${{ '
                                                            'steps.current_head.outputs.artifact_digest '
                                                            '}}',
   'NICO_BOUND_STEPS_CURRENT_HEAD_OUTPUTS_ARTIFACT_ID': '${{ '
                                                        'steps.current_head.outputs.artifact_id }}',
   'NICO_BOUND_STEPS_CURRENT_HEAD_OUTPUTS_ARTIFACT_NAME': '${{ '
                                                          'steps.current_head.outputs.artifact_name '
                                                          '}}',
   'NICO_BOUND_STEPS_CURRENT_HEAD_OUTPUTS_IOS_RUN_ID': '${{ steps.current_head.outputs.ios_run_id '
                                                       '}}',
   'NICO_BOUND_STEPS_CURRENT_HEAD_OUTPUTS_MOBILE_RUN_ID': '${{ '
                                                          'steps.current_head.outputs.mobile_run_id '
                                                          '}}'}),
 ('.github/workflows/phase10-real-validation.yml',
  'Record exact revision',
  {'NICO_BOUND_GITHUB_EVENT_PULL_REQUEST_HEAD_SHA_GITHUB_SHA': '${{ '
                                                               'github.event.pull_request.head.sha '
                                                               '|| github.sha }}'}),
 ('.github/workflows/phase11-client-workflow-hardening.yml',
  'Verify exact revision and compile',
  {'NICO_BOUND_GITHUB_EVENT_PULL_REQUEST_HEAD_SHA_GITHUB_SHA': '${{ '
                                                               'github.event.pull_request.head.sha '
                                                               '|| github.sha }}'}),
 ('.github/workflows/phase12-production-release-baseline.yml',
  'Verify exact revision and compile',
  {'NICO_BOUND_GITHUB_EVENT_PULL_REQUEST_HEAD_SHA_GITHUB_SHA': '${{ '
                                                               'github.event.pull_request.head.sha '
                                                               '|| github.sha }}'}),
 ('.github/workflows/resilience-proof.yml',
  'Build restart recovery and degradation proof',
  {'NICO_BOUND_GITHUB_RUN_ATTEMPT': '${{ github.run_attempt }}',
   'NICO_BOUND_GITHUB_RUN_ID': '${{ github.run_id }}'}),
 ('.github/workflows/spanish-comprehensive-production-proof.yml',
  'Require passing authenticated Spanish final-report evidence',
  {'NICO_BOUND_STEPS_EXCLUSION_PROOF_OUTCOME': '${{ steps.exclusion_proof.outcome }}',
   'NICO_BOUND_STEPS_FRESH_BROWSER_MATRIX_OUTCOME': '${{ steps.fresh_browser_matrix.outcome }}',
   'NICO_BOUND_STEPS_SPANISH_PROOF_OUTCOME': '${{ steps.spanish_proof.outcome }}',
   'NICO_BOUND_STEPS_SPANISH_RECOVERY_OUTCOME': '${{ steps.spanish_recovery.outcome }}'}),
 ('.github/workflows/two-service-production-acceptance.yml',
  'Require passing live evidence contract',
  {'NICO_BOUND_STEPS_ACCEPTANCE_OUTCOME': '${{ steps.acceptance.outcome }}',
   'NICO_BOUND_STEPS_PHASE1_AUDIT_OUTCOME': '${{ steps.phase1_audit.outcome }}'})]


def test_workflow_binding_contracts():
    for path, step, bindings in BINDINGS:
        source = (ROOT / path).read_text()
        block = source.split("      - name: " + step + "\n", 1)[1].split("\n      - name:", 1)[0]
        header, body = block.split("        run: |\n", 1)
        for name, expression in bindings.items():
            assert "          " + name + ": " + expression in header
            assert "${" + name + "}" in body
            assert expression not in body.split("<<'PY'", 1)[0]
        shell = "\n".join(line[10:] for line in body.splitlines() if line.startswith("          "))
        # Unchanged Python heredoc expressions are rendered only for bash syntax validation.
        shell = re.sub(r"\$\{\{.*?\}\}", "fixture", shell)
        result = subprocess.run(["bash", "-n"], input=shell, text=True, capture_output=True)
        assert result.returncode == 0, (path, result.stderr)


def test_quoted_binding_preserves_literal_argument():
    for value in ["main", "feature/release", 'a b;$(false)"quoted']:
        result = subprocess.check_output(
            ["bash", "-c", 'printf "%s" "${NICO_BOUND_VALUE}"'],
            env={"NICO_BOUND_VALUE": value}, text=True,
        )
        assert result == value
