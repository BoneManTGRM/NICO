"""Native finding provenance must survive report normalization without target credit."""
from copy import deepcopy

import pytest

from nico.comprehensive_native_providers_v5 import (
    _normalized_record, build_canonical_scanner_finding_register,
)
from nico.comprehensive_truth_reconciliation_v7 import _enrich_candidate

COMMIT = "bb5296576e8f1a9fc11c19d9a25ba02ed4547e24"


def native(origin="toolchain"):
    path = "/usr/local/lib/gcc/x86_64-linux-gnu/14.2.0/include/cpuid.h"
    return {
        "path": path, "line": 325, "column": 21,
        "rule_id": "constParameterPointer", "severity": "style",
        "message": "Owned retained native diagnostic model.",
        "origin": origin, "source_sha256": "a" * 64,
        "locations": [{"origin": origin, "path": path, "source_sha256": "a" * 64,
                       "line": 325, "column": 21}],
    }


def normalized(finding):
    return _normalized_record(commit_sha=COMMIT, scanner="cppcheck",
                              category="static", finding=finding)


@pytest.mark.parametrize("origin", ["toolchain", "compiler_predefines", "original", "generated"])
def test_native_origin_hash_and_full_locations_survive_without_mutating_raw(origin):
    finding = native(origin)
    before = deepcopy(finding)
    record = normalized(finding)
    assert finding == before
    for field in ("origin", "source_sha256", "locations"):
        assert record[field] == finding[field]
    record["locations"][0]["line"] = 999
    assert finding == before


@pytest.mark.parametrize("origin", ["toolchain", "compiler_predefines"])
def test_external_native_inputs_retain_evidence_without_exact_target_source_credit(origin):
    finding = native(origin)
    # Test-like path names must not overwrite an explicitly external origin.
    finding["path"] = "/usr/local/include/tests/owned.h"
    record = _enrich_candidate(normalized(finding))
    assert record["evidence_quality"] == "source_path"
    assert record["production_classification"] == "external_toolchain"
    assert record["exact_commit_sha"] == COMMIT  # Assessment identity stays bound.
    assert record["human_review_required"] is True
    assert record["human_disposition"] is None
    assert record["reviewer_identity"] is None
    assert record["review_timestamp"] is None
    assert record["disposition"] == "review_required"


@pytest.mark.parametrize("field", ["origin", "source_sha256", "locations"])
def test_distinct_native_provenance_changes_finding_and_supporting_evidence_identity(field):
    first = native()
    second = deepcopy(first)
    if field == "origin":
        second[field] = "compiler_predefines"
    elif field == "source_sha256":
        second[field] = "b" * 64
    else:
        second[field][0]["line"] += 1
    left = _enrich_candidate(normalized(first))
    right = _enrich_candidate(normalized(second))
    assert left["finding_id"] != right["finding_id"]
    assert left["supporting_evidence_digest_sha256"] != right["supporting_evidence_digest_sha256"]
    assert left["duplicate_group_id"] != right["duplicate_group_id"]


def test_same_native_coordinate_with_distinct_source_hashes_does_not_collapse():
    first = native()
    second = deepcopy(first)
    second["source_sha256"] = "b" * 64
    scan = {
        "scanner_results": [{"scanner_name": "cppcheck", "category": "static",
                             "findings": [first, second]}],
        "finding_summary": {"by_tool": {"cppcheck": {"raw": 2, "review_required": 2}}},
    }
    result = build_canonical_scanner_finding_register(scan, COMMIT)
    assert len(result["findings"]) == 2
    assert {row.get("source_sha256") for row in result["findings"]} == {"a" * 64, "b" * 64}
    assert all(row["evidence_quality"] != "count_only" for row in result["findings"])
    assert result["totals"]["raw"] == 2
    assert result["totals"]["review_required"] == 2
    assert result["totals"]["exact_source"] == 0
    assert result["totals"]["source_path"] == 2
    assert result["totals"]["excluded_test_only"] == 0
    assert result["count_parity_verified"] is True


def test_assessed_source_coordinate_keeps_existing_exact_source_quality():
    finding = native("original")
    finding["path"] = "src/owned.cpp"
    record = normalized(finding)
    assert record["evidence_quality"] == "exact_source"
    assert record["origin"] == "original"
    assert record["source_sha256"] == "a" * 64


def test_legacy_record_without_native_provenance_keeps_existing_identity():
    finding = {
        "path": "src/owned.cpp", "line": 7, "column": 3,
        "rule_id": "style", "severity": "style", "message": "Owned legacy fixture.",
    }
    record = normalized(finding)
    # Original v5 fingerprint from fixed conditions is retained in the reproduction.
    assert record["raw_fingerprint"] == "0eb37989cdd804f2bc1776c339ca7269194ee367abd887978a87e07afaf2e8d3"
    assert not any(field in record for field in ("origin", "source_sha256", "locations"))
    assert record["evidence_quality"] == "exact_source"


def test_native_duplicate_expansion_preserves_bound_supporting_evidence():
    from nico.comprehensive_candidate_identity_v1 import expand_candidate_identities
    from nico.comprehensive_truth_reconciliation_v7 import reconciled_build_register

    first = native()
    second = deepcopy(first)
    scan = {
        "scanner_results": [{"scanner_name": "cppcheck", "category": "static",
                             "findings": [first, second]}],
        "finding_summary": {"by_tool": {"cppcheck": {"raw": 2, "review_required": 2}}},
    }
    register = reconciled_build_register(scan, COMMIT)
    assert len(register["findings"]) == 1
    expected = register["findings"][0]["supporting_evidence_digest_sha256"]
    result = expand_candidate_identities(register)
    assert len(result["findings"]) == 2
    assert len({row["candidate_id"] for row in result["findings"]}) == 2
    assert all(row["supporting_evidence_digest_sha256"] == expected for row in result["findings"])
    assert all(row["source_sha256"] == first["source_sha256"] for row in result["findings"])
    assert all(row["locations"] == first["locations"] for row in result["findings"])
    assert all(row["production_classification"] == "external_toolchain" for row in result["findings"])
    assert result["totals"]["raw"] == result["totals"]["source_path"] == 2
    assert result["candidate_record_count_matches_raw"] is True
    assert result["candidate_evidence_quality_totals_match_source"] is True

def test_native_duplicate_supporting_evidence_changes_with_provenance():
    from nico.comprehensive_candidate_identity_v1 import expand_candidate_identities
    from nico.comprehensive_truth_reconciliation_v7 import reconciled_build_register

    digests = []
    for sha in ("a" * 64, "b" * 64):
        finding = native()
        finding["source_sha256"] = sha
        finding["locations"][0]["source_sha256"] = sha
        scan = {
            "scanner_results": [{"scanner_name": "cppcheck", "category": "static",
                                 "findings": [finding, deepcopy(finding)]}],
            "finding_summary": {"by_tool": {"cppcheck": {"raw": 2, "review_required": 2}}},
        }
        result = expand_candidate_identities(reconciled_build_register(scan, COMMIT))
        digests.append({row["supporting_evidence_digest_sha256"] for row in result["findings"]})
    assert digests[0].isdisjoint(digests[1])


@pytest.mark.parametrize("bootstrap", [
    "nico.api.specialist_ship_ready_bootstrap",
    "nico.api.final_report_worker_bootstrap",
])
def test_installed_report_paths_preserve_native_provenance_in_both_locales(bootstrap):
    import json
    import subprocess
    import sys
    from pathlib import Path

    script = """
import base64, hashlib, importlib, io, json
from copy import deepcopy
from pypdf import PdfReader
importlib.import_module(BOOTSTRAP)
from nico import comprehensive_native_providers_v5 as providers
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.comprehensive_same_run_locale_report_v1 import build_same_run_locale_report
from tests.test_v2_premium_report_renderer import _package

finding = FINDING
finding["locations"].append({"origin":"original", "path":"src/owned.cpp",
                             "source_sha256":"b"*64, "line":7, "column":3})
scan = {"status":"complete",
        "scanner_results":[{"scanner_name":"cppcheck","category":"static",
                            "findings":[finding,deepcopy(finding)]}],
        "finding_summary":{"by_tool":{"cppcheck":{"raw":2,"review_required":2}}}}
before = deepcopy(scan)
register = providers.build_canonical_scanner_finding_register(scan, COMMIT)
assert scan == before
assert register["candidate_record_count"] == register["totals"]["raw"] == 2
assert register["totals"]["source_path"] == 2
assert register["totals"]["exact_source"] == 0
rows = register["findings"]
assert len({row["candidate_id"] for row in rows}) == 2
assert all(row["locations"] == finding["locations"] for row in rows)
assert all(row["production_classification"] == "external_toolchain" for row in rows)
assert all(row["source_sha256"] == "a"*64 for row in rows)
assert all(row["human_review_required"] is True for row in rows)
assert all(row.get("human_disposition") is None for row in rows)
summaries = []
for language in ("en", "es-MX"):
    package = _package(language)["json"]
    package["identity"].update({"commit_sha":COMMIT,
        "run_id":"comprun_owned_native_provenance", "repository":"owned/native-fixture"})
    package["assessment"]["canonical_scanner_finding_register"] = deepcopy(register)
    package["assessment"]["human_review_required"] = True
    package["assessment"]["client_delivery_allowed"] = False
    package["human_review_required"] = True
    package["client_delivery_allowed"] = False
    package["report_id"] = "comprehensive_report_owned_native_provenance_"+language
    exported = rebuild_client_artifacts({"json":package})
    canonical = exported["json"]
    retained = canonical["assessment"]["canonical_scanner_finding_register"]
    # Client display paths follow the existing repository-relative contract;
    # origin/content identity and raw evidence remain unchanged.
    expected_rows = deepcopy(register["findings"])
    for row in expected_rows:
        row["path"] = row["source_path"] = "lib/gcc/x86_64-linux-gnu/14.2.0/include/cpuid.h"
        row["locations"][0]["path"] = row["source_path"]
    assert retained["findings"] == expected_rows
    assert retained["totals"] == register["totals"]
    assert canonical["identity"]["commit_sha"] == COMMIT
    assert canonical["assessment"]["human_review_required"] is True
    assert canonical["assessment"]["client_delivery_allowed"] is False
    pdf = base64.b64decode(exported["pdf_base64"], validate=True)
    assert exported["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert pdf.startswith(b"%PDF-") and len(PdfReader(io.BytesIO(pdf)).pages) > 0
    assert exported["markdown"] and exported["html"]
    status = {"run_id":canonical["identity"]["run_id"],"repository":canonical["identity"]["repository"],
        "commit_sha":COMMIT,"evidence_ledger_id":canonical["identity"].get("evidence_ledger_id"),
        "report_language":language,"terminal":True,"human_review_required":True,
        "human_review_completed":False,"client_delivery_allowed":False,"reports":exported}
    first = build_same_run_locale_report(status, language)
    second = build_same_run_locale_report(status, language)
    assert first["report"]["pdf_base64"] == second["report"]["pdf_base64"] == exported["pdf_base64"]
    assert first["report"]["pdf_sha256"] == second["report"]["pdf_sha256"] == exported["pdf_sha256"]
    assert first["report"]["json"] == second["report"]["json"] == canonical
    assert first["assessment_rerun"] is False
    assert first["approval_state_mutated"] is False
    assert first["delivery_state_mutated"] is False
    assert first["client_delivery_allowed"] is False
    summaries.append({"language":language,"pdf_sha256":exported["pdf_sha256"],
        "candidate_ids":[r["candidate_id"] for r in retained["findings"]],
        "provenance_preserved":True,"human_review_completed":False})
assert summaries[0]["candidate_ids"] == summaries[1]["candidate_ids"]
changed_finding = deepcopy(finding)
changed_finding["source_sha256"] = "c"*64
changed_finding["locations"][0]["source_sha256"] = "c"*64
changed_scan = deepcopy(scan)
changed_scan["scanner_results"][0]["findings"] = [changed_finding,deepcopy(changed_finding)]
changed_register = providers.build_canonical_scanner_finding_register(changed_scan, COMMIT)
assert changed_register["totals"] == register["totals"]
assert {row["candidate_id"] for row in changed_register["findings"]}.isdisjoint(
    {row["candidate_id"] for row in register["findings"]})
assert {row["supporting_evidence_digest_sha256"] for row in changed_register["findings"]}.isdisjoint(
    {row["supporting_evidence_digest_sha256"] for row in register["findings"]})
changed_package = deepcopy(package)
changed_package["assessment"]["canonical_scanner_finding_register"] = changed_register
changed_export = rebuild_client_artifacts({"json":changed_package})
assert changed_export["canonical_truth_sha256"] != exported["canonical_truth_sha256"]
assert all(row["source_sha256"] == "c"*64 for row in
    changed_export["json"]["assessment"]["canonical_scanner_finding_register"]["findings"])
assert changed_export["json"]["assessment"]["client_delivery_allowed"] is False
assert scan == before
print(json.dumps({"bootstrap":BOOTSTRAP,"owned_fixture":True,"summaries":summaries}))
"""
    prelude = "BOOTSTRAP=" + repr(bootstrap) + "\nFINDING=" + repr(native()) + "\nCOMMIT=" + repr(COMMIT) + "\n"
    result = subprocess.run([sys.executable, "-c", prelude + script],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr[-5000:]
