"""Retained scanner transport must not lose or manufacture acceptance evidence."""
from copy import deepcopy

import pytest

from nico.complete_assessment_gate_v1 import REQUIRED_TOOLS, complete_assessment_evidence
from nico.comprehensive_authoritative_scanner_truth_v62 import reconcile_authoritative_scanner_truth
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
from nico.v2_scanner_reconciliation import normalize_record

SHA = "a" * 40
RUN = "comprun_" + "b" * 32
RAW_SHA = "c" * 64
RECORD_SHA = "d" * 64
REASON = (
    "No declared package source exists in the completely inspected snapshot; "
    "OSV dependency matching is not applicable to the supplied evidence. "
    "Undeclared dependencies were not assessed."
)


def scanner_result(tool):
    return {
        "tool": tool, "status": "completed", "returncode": 0,
        "commit_sha": SHA, "current_run": True,
        "execution_observed_for_this_report": True,
        "verified_for_this_report": True, "output_capture_complete": True,
        "returncode_valid": True, "raw_artifact_retention_complete": True,
        "raw_artifact_sha256": RAW_SHA, "artifact_hash": RECORD_SHA,
        "raw_artifact": {"sha256": RAW_SHA, "storage_key": "private/do-not-copy"},
        "findings": [],
    }


def no_packages():
    record = scanner_result("osv-scanner")
    record.update({
        "status": "not_applicable", "applicable": False,
        "evidence_required": False, "completed": False, "verified": False,
        "verified_complete": False, "verified_for_this_report": False,
        "returncode": 128, "returncode_valid": False,
        "reason": REASON, "applicability_reason": REASON,
        "native_json_output": False, "no_vulnerabilities_claimed": False,
        "applicability_evidence": {
            "schema": "nico.osv-package-inventory.v1", "inventory_complete": True,
            "no_declared_package_sources": True, "package_source_paths": [],
            "inventory_sha256": "e" * 64,
        },
    })
    return record


def compact(records):
    return compact_scanner_records({
        "scan_id": "scan_transport_fixture", "snapshot_commit_sha": SHA,
        "actual_commit_sha": SHA, "snapshot_match": True,
        "scanner_results": records,
    }, commit_sha=SHA)


def canonical(records):
    return {"identity": {"commit_sha": SHA, "run_id": RUN},
            "requested_scanner_records": records,
            "assessment": {"requested_scanner_records": deepcopy(records)},
            "human_review_required": True, "client_delivery_allowed": False}


def test_compact_record_retains_raw_digest_without_copying_private_storage_path():
    raw = scanner_result("bandit")
    original = deepcopy(raw)
    result = compact([raw])[0]
    assert result.get("raw_artifact_sha256") == RAW_SHA
    assert result["artifact_hash"] == RECORD_SHA
    assert "raw_artifact" not in result
    assert raw == original


def test_no_package_inventory_survives_normalization_and_compaction_without_scan_credit():
    raw = no_packages()
    original = deepcopy(raw)
    normalized = normalize_record(raw, SHA)
    assert normalized["status"] == "not_applicable"
    result = compact([normalized])[0]
    assert result["status"] == "not_applicable"
    assert result.get("applicable") is False
    assert result.get("applicability_evidence") == original["applicability_evidence"]
    assert result.get("applicability_reason") == REASON
    assert not any(result.get(k) is True for k in
                   ("completed", "verified", "verified_complete", "verified_for_this_report"))
    assert raw == original


def test_compaction_and_authoritative_reconciliation_preserve_complete_assessment_contract():
    raw = [no_packages() if t == "osv-scanner" else scanner_result(t) for t in REQUIRED_TOOLS]
    projected = reconcile_authoritative_scanner_truth(canonical(compact(raw)))
    proof = complete_assessment_evidence(projected, expected_commit=SHA, expected_run=RUN)
    assert proof["passed"], proof["failures"]
    assert proof["not_applicable_tools"] == ["osv-scanner"]
    assert "osv-scanner" not in proof["completed_tools"]
    assert len(proof["completed_tools"]) == 8
    assert proof["client_delivery_allowed"] is False
    assert proof["human_approval_proven"] is False


@pytest.mark.parametrize("missing", ["raw_artifact_sha256", "raw_artifact_retention_complete"])
def test_record_hash_never_substitutes_for_missing_raw_evidence(missing):
    raw = scanner_result("bandit")
    raw.pop("raw_artifact")
    raw.pop(missing)
    result = compact([raw])[0]
    proof = complete_assessment_evidence(canonical([result]), expected_commit=SHA, expected_run=RUN)
    assert "bandit:raw_scanner_evidence_missing" in proof["failures"]


def test_explicit_failed_retention_cannot_be_promoted_by_a_record_hash():
    raw = scanner_result("bandit")
    raw["raw_artifact_retention_complete"] = False
    result = compact([raw])[0]
    assert result["raw_artifact_retention_complete"] is False
    assert result["completed"] is False


def test_invalid_package_inventory_still_fails_the_unchanged_acceptance_gate():
    raw = no_packages()
    raw["applicability_evidence"]["inventory_complete"] = False
    result = compact([raw])[0]
    proof = complete_assessment_evidence(canonical([result]), expected_commit=SHA, expected_run=RUN)
    assert "osv-scanner:no_package_inventory_unverified" in proof["failures"]


def test_explicit_wrong_source_commit_is_not_relabelled_as_the_expected_commit():
    raw = scanner_result("bandit")
    raw["commit_sha"] = "f" * 40
    result = compact([raw])[0]
    assert result["commit_sha"] == "f" * 40
    assert result["exact_commit_match"] is False


@pytest.mark.parametrize("bootstrap", [
    "nico.api.specialist_ship_ready_bootstrap",
    "nico.api.final_report_worker_bootstrap",
])
def test_actual_bootstraps_keep_transport_proof_through_technology_exclusions(bootstrap):
    import subprocess
    import sys
    from pathlib import Path

    script = r'''
import importlib, runpy
importlib.import_module(BOOTSTRAP)
f = runpy.run_path('tests/test_compact_scanner_acceptance_transport.py')
raw = [f['no_packages']() if t == 'osv-scanner' else f['scanner_result'](t)
       for t in f['REQUIRED_TOOLS']]
for record in raw:
    reasons = {'pip-audit': 'requirements.txt was not found.',
               'npm-audit': 'No package-lock.json with an adjacent package.json was found.',
               'typescript': 'apps/web/tsconfig.json or the exact local TypeScript compiler is missing.'}
    if record['tool'] in reasons:
        record.update(status='unavailable', reason=reasons[record['tool']],
                      raw_artifact_retention_complete=False, verified_for_this_report=False,
                      output_capture_complete=False)
        record.pop('raw_artifact_sha256')
        record.pop('raw_artifact')
        if record['tool'] == 'typescript':
            # This input models an explicit technology-exclusion observation,
            # not the ambiguous missing-compiler message (tested separately).
            record.update(status='not_applicable', applicable=False,
                          applicability_reason='No TypeScript project, source tree, or tsconfig exists at the assessed commit; TypeScript compilation is not applicable to this repository snapshot.')
report = f['reconcile_authoritative_scanner_truth'](f['canonical'](f['compact'](raw)))
proof = f['complete_assessment_evidence'](report, expected_commit=f['SHA'], expected_run=f['RUN'])
assert proof['passed'], proof['failures']
assert set(proof['not_applicable_tools']) == {'osv-scanner', 'pip-audit', 'npm-audit', 'typescript'}
assert len(proof['completed_tools']) == 5
assert proof['client_delivery_allowed'] is False
'''
    result = subprocess.run([sys.executable, "-c", f"BOOTSTRAP={bootstrap!r}\n" + script],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr[-5000:]


def test_missing_typescript_compiler_is_not_invented_as_an_exclusion():
    raw = scanner_result("typescript")
    raw.update(status="unavailable", output_capture_complete=False,
               raw_artifact_retention_complete=False, verified_for_this_report=False,
               reason="apps/web/tsconfig.json or the exact local TypeScript compiler is missing.")
    projected = reconcile_authoritative_scanner_truth(canonical(compact([raw])))
    proof = complete_assessment_evidence(projected, expected_commit=SHA, expected_run=RUN)
    assert not proof["passed"]
    assert "typescript:scanner_incomplete:unavailable" in proof["failures"]
    assert "typescript" not in proof["not_applicable_tools"]


def test_not_applicable_cannot_restore_a_stale_raw_verified_flag():
    raw = no_packages()
    raw["verified_for_this_report"] = True
    result = compact([raw])[0]
    assert result["verified_for_this_report"] is False
    assert result["completed"] is False


@pytest.mark.parametrize("bootstrap", [
    "nico.api.specialist_ship_ready_bootstrap",
    "nico.api.final_report_worker_bootstrap",
])
def test_live_injection_replaces_stale_requested_projection_before_full_normalization(bootstrap):
    import subprocess
    import sys
    from pathlib import Path

    script = r'''
import importlib, runpy
from copy import deepcopy
importlib.import_module(BOOTSTRAP)
f = runpy.run_path('tests/test_compact_scanner_acceptance_transport.py')
from nico.v2_production_authority import _inject_live_runtime_truth
from nico import phase9_comprehensive_report_integration_v1 as integration
raw = [f['no_packages']() if t == 'osv-scanner' else f['scanner_result'](t)
       for t in f['REQUIRED_TOOLS']]
records = f['compact'](raw)
stale = deepcopy(records)
for record in stale:
    record.pop('raw_artifact_sha256', None)
    if record['tool'] == 'osv-scanner':
        record.update(status='unavailable', state='unavailable', applicable=True)
        record.pop('applicability_reason', None)
        record.pop('applicability_evidence', None)
source = {'report_package': {'json': f['canonical'](stale)}}
context = {'run_id': f['RUN'], 'commit_sha': f['SHA'], 'report_language': 'en',
    'prior_stage_results': {'dependency_security_static_analysis': {
        'scanner_execution_records': records,
        'scanner': {'scan_id': 'scan_transport_fixture',
            'tools_requested': list(f['REQUIRED_TOOLS']),
            'actual_commit_sha': f['SHA'], 'snapshot_match': True}}}}
original_source, original_context = deepcopy(source), deepcopy(context)
result = _inject_live_runtime_truth(source, context)
canonical = integration.normalize_canonical_report(result['report_package']['json'])
proof = f['complete_assessment_evidence'](canonical, expected_commit=f['SHA'], expected_run=f['RUN'])
assert proof['passed'], proof['failures']
assert proof['not_applicable_tools'] == ['osv-scanner']
assert source == original_source and context == original_context
assert canonical['human_review_required'] is True
assert canonical['client_delivery_allowed'] is False

# Fresh retained evidence with an explicitly wrong source is not rescued by the
# older report projection, even when that projection claims the expected source.
bad = deepcopy(context)
for record in bad['prior_stage_results']['dependency_security_static_analysis']['scanner_execution_records']:
    if record['tool'] == 'bandit':
        for key in ('commit_sha', 'snapshot_commit_sha', 'target_commit_sha'):
            record[key] = 'f' * 40
        record['exact_commit_match'] = False
bad_result = _inject_live_runtime_truth(source, bad)
bad_canonical = integration.normalize_canonical_report(bad_result['report_package']['json'])
bad_proof = f['complete_assessment_evidence'](bad_canonical, expected_commit=f['SHA'], expected_run=f['RUN'])
assert 'bandit:source_identity_unverified' in bad_proof['failures']
assert bad_proof['passed'] is False
'''
    result = subprocess.run([sys.executable, "-c", f"BOOTSTRAP={bootstrap!r}\n" + script],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr[-5000:]
