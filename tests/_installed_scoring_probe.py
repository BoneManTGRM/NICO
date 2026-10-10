"""Subprocess fixture: production bindings, in-memory retained inputs, no network."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import socket
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
bootstrap = importlib.import_module(sys.argv[1])
language = sys.argv[2]

from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v5 as scoring
from nico import comprehensive_candidate_volume_assurance_v2 as workload
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.node_scanner_applicability_v1 import inspect_node_inputs, justified_inapplicability
from tests.test_comprehensive_native_providers_v4 import _context, _repo, TOOLS
from tests.test_comprehensive_native_providers_v5 import _scan
from tests.test_comprehensive_final_artifact_endpoint_integrity_v1 import RUN_ID, LEDGER_ID


def forbidden_network(*args, **kwargs):
    raise AssertionError("Owned scoring controls must not open network connections")


socket.create_connection = forbidden_network
socket.socket.connect = forbidden_network
provider = getattr(bootstrap.app.state, PROVIDER_STATE_KEY)["canonical_scoring"]
SHA = "a" * 40  # Explicit synthetic source identity, not a historical repository SHA.
sources = {
    "python": {"src/main.py": "def total(a, b):\n    return a + b\n", "requirements.txt": ""},
    "node": {"src/main.ts": "export const total = (a: number, b: number) => a + b;\n", "package.json": '{"name":"owned"}', "package-lock.json": "{}"},
}
sources["mixed"] = {**sources["python"], **sources["node"]}
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for path, content in sources[language].items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    inventory = inspect_node_inputs(root, SHA)

base = _scan(static_review=0, include_payload=True)
base.update(actual_commit_sha=SHA, repository=f"owned/{language}-fixture")
for counts in base["finding_summary"]["by_tool"].values():
    counts.update({key: 0 for key in counts})
absent = []
raw_captures = {}
for record in base["scanner_results"]:
    tool = record["scanner_name"]
    record.update(status="completed", findings=[], commit_sha=SHA)
    # Owned deterministic capture bytes, not a claim of real analyzer execution.
    capture = json.dumps({"fixture": "owned-synthetic-capture", "scanner": tool,
                          "commit_sha": SHA, "findings": []}, sort_keys=True).encode()
    raw_captures[tool] = capture
    record.update(capture_complete=True, artifact_sha256=hashlib.sha256(capture).hexdigest(), exit_code=0)
    if justified_inapplicability(inventory, tool, SHA):
        absent.append(tool)
        record.clear()
        record.update(scanner_name=tool, status="not_applicable", completed=False,
                      verified=False, execution_observed_for_this_report=False,
                      commit_sha=SHA, applicability_evidence=deepcopy(inventory))

context = _context()
context.update(repository=base["repository"], run_id=RUN_ID, evidence_ledger_id=LEDGER_ID)
repo = _repo()
repo.update(repository=context["repository"], commit_sha=SHA)
repo["file_evidence"] = {"sampled_paths": sorted(sources[language])}
repo["dependency_evidence"]["lockfile_paths"] = ["requirements.txt"] if language == "python" else ["package-lock.json"]
context["prior_stage_results"] = {
    "repository_and_delivery_evidence": {
        "repository_evidence": repo,
        "complexity_evidence": {"complexity_score": 78, "files_analyzed": len(sources[language]), "risk_level": "moderate"},
    },
    "dependency_security_static_analysis": {"scan_id": "owned-fixed-scoring"},
}


def run(scan, *, reverse=False):
    fixture = deepcopy(scan)
    if reverse:
        fixture["scanner_results"].reverse()
        fixture["finding_summary"]["by_tool"] = dict(reversed(list(fixture["finding_summary"]["by_tool"].items())))
    legacy.get_scan = lambda scan_id: deepcopy(fixture) if scan_id == "owned-fixed-scoring" else forbidden_network()
    before = deepcopy(context)
    fixture_before = deepcopy(fixture)
    result = provider(deepcopy(context))
    assert context == before and fixture == fixture_before
    return result


def scores(result):
    a = result["assessment"]
    return a["technical_score"], a["canonical_evidence_adjusted_score"]


observations = {}
for case in ("clean", "incomplete", "material", "review_1", "review_25"):
    scan = deepcopy(base)
    semgrep = next(r for r in scan["scanner_results"] if r.get("scanner_name") == "semgrep")
    if case == "incomplete":
        semgrep.update(status="failed", completed=False, verified=False, raw_artifact_retention_complete=False)
    elif case == "material" or case.startswith("review_"):
        count = 1 if case == "material" else int(case.split("_")[1])
        is_material = case == "material"
        semgrep["findings"] = [{
            "check_id": f"owned.rule.{index}",
            "path": "src/main.py" if language == "python" else "src/main.ts",
            "start": {"line": 1, "col": 1},
            "extra": {"message": f"Owned retained observation {index}", "severity": "INFO"},
            "disposition": "verified_material" if is_material else "review_required",
        } for index in range(count)]
        scan["finding_summary"]["by_tool"]["semgrep"].update(raw=count, material=int(is_material), review_required=0 if is_material else count)
    capture = json.dumps({"fixture": "owned-synthetic-capture", "scanner": "semgrep",
                          "commit_sha": SHA, "findings": semgrep["findings"]}, sort_keys=True).encode()
    semgrep["artifact_sha256"] = hashlib.sha256(capture).hexdigest()
    first, second, reordered = run(scan), run(scan), run(scan, reverse=True)
    assert first["status"] == second["status"] == reordered["status"] == "complete", (case, first)
    assert first == second, case
    assert scores(first) == scores(second) == scores(reordered), case
    a = first["assessment"]
    sections = {s["id"]: s for s in a["sections"]}
    expected_static = 80 if case == "material" else 88 if case == "incomplete" else 96
    assert sections["static_analysis"]["presented_score"] == expected_static
    assert sections["dependency_health"]["presented_score"] == 96
    assert sections["secrets_review"]["presented_score"] == 96
    # Recompute both totals from independent retained obligations and section values.
    technical = round(sum(s["presented_score"] for s in sections.values()) / len(sections))
    adjusted = technical - (4 if case == "incomplete" else 0)
    assert scores(first) == (technical, adjusted), case
    coverage = a["evidence_coverage"]
    assert sorted(coverage["not_applicable_analyzers"]) == sorted(absent)
    assert not set(absent).intersection(coverage["completed_analyzers"])
    assert coverage["not_applicable_receives_completion_credit"] is False
    assert first["commit_sha"] == SHA and first["repository"] == context["repository"]
    assert first["evidence_ledger_id"] == context["evidence_ledger_id"]
    assert a["score_contract"]["version"] == scoring.VERSION
    assert reordered["assessment"]["score_contract"]["version"] == scoring.VERSION
    observations[case] = scores(first)
    if case == "clean":
        retained = first

assert observations["clean"] == observations["review_1"] == observations["review_25"]
print(json.dumps({"bootstrap": sys.argv[1], "language": language, "scores": observations,
                  "source_fixture_sha256": hashlib.sha256(json.dumps(sources[language], sort_keys=True).encode()).hexdigest(),
                  "evidence_sha256": hashlib.sha256(json.dumps({"context": context, "scan": base}, sort_keys=True).encode()).hexdigest(),
                  "scoring_version": scoring.VERSION, "workload_version": workload.VERSION}), flush=True)

identity_results = {}
def rejection(result):
    assessment = result.get("assessment") or {}
    containers = (assessment, assessment.get("maturity_signal") or {}, assessment.get("score_contract") or {})
    names = ("score", "technical_score", "canonical_technical_score", "evidence_adjusted_score", "canonical_evidence_adjusted_score")
    return {"status": result["status"], "numeric_score_present": any(
        isinstance(container.get(name), (int, float))
        for container in containers for name in names
    )}

for field, wrong in (("repository", "owned/different-fixture"), ("actual_commit_sha", "b" * 40), ("snapshot_commit_sha", "b" * 40)):
    scan = deepcopy(base)
    scan[field] = wrong
    result = run(scan)
    identity_results[field] = rejection(result)
scan = deepcopy(base)
scan["scanner_results"][0]["commit_sha"] = "b" * 40
result = run(scan)
identity_results["record_commit_sha"] = rejection(result)
repo["repository"] = "owned/different-fixture"
result = run(base)
repo["repository"] = context["repository"]
identity_results["repository_evidence"] = rejection(result)
print(json.dumps({"identity_rejection": identity_results}), flush=True)
assert all(value == {"status": "blocked", "numeric_score_present": False} for value in identity_results.values()), identity_results

# The storage value changes after the first read. Every scoring layer must use
# the one validated snapshot; the next invocation must reject the changed source.
storage_reads = []
wrong_source = deepcopy(base)
wrong_source["repository"] = "owned/different-fixture"
def changing_storage(scan_id):
    storage_reads.append(scan_id)
    return deepcopy(base if len(storage_reads) == 1 else wrong_source)
legacy.get_scan = changing_storage
assert scores(provider(deepcopy(context))) == observations["clean"]
assert len(storage_reads) == 1, storage_reads
assert rejection(provider(deepcopy(context))) == {"status": "blocked", "numeric_score_present": False}
assert len(storage_reads) == 2
# Deduplication must not hide a stale source row, in either input order.
conflicting = deepcopy(base)
stale = deepcopy(conflicting["scanner_results"][0])
stale["commit_sha"] = "b" * 40
conflicting["scanner_results"].insert(0, stale)
for reverse in (False, True):
    assert rejection(run(conflicting, reverse=reverse)) == {"status": "blocked", "numeric_score_present": False}
# A sole explicit claim on an overwritten duplicate must also survive folding.
conflicting.pop("repository")
conflicting["scanner_results"][0].update(commit_sha=SHA, repository="owned/different-fixture")
for reverse in (False, True):
    assert rejection(run(conflicting, reverse=reverse)) == {"status": "blocked", "numeric_score_present": False}
print(json.dumps({"single_snapshot_storage_reads": len(storage_reads), "duplicate_identity_rejected_both_orders": True}), flush=True)

# Exercise actual artifact assembly, locale rendering and read-only API retrieval.
# This does not substitute for scanner execution or a live browser acceptance run.
from fastapi.testclient import TestClient
from tests.test_v2_premium_report_renderer import _package
from tests.test_comprehensive_final_artifact_endpoint_integrity_v1 import _app, _record_with_canonical_final_report, FINAL_STAGE
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico import comprehensive_same_run_locale_report_v1 as locale

package = _package("en")
canonical = package["json"]
canonical["identity"].update({key: context[key] for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")})
canonical["assessment"] = deepcopy(retained["assessment"])
canonical["assessment"]["report_language"] = "en"
canonical["canonical_findings"] = []
canonical["roadmap"] = []
canonical["scanner_execution_records"] = deepcopy(base["scanner_results"])
canonical["repository_evidence"] = deepcopy(repo)
# The retained capture contract rejects missing/truncated or wrong-source proof.
from nico.comprehensive_authoritative_scanner_truth_v62 import _phase14_records
from nico.phase14_analyzer_evidence_v1 import AnalyzerEvidenceError, normalize_record
proof = next(record for record in _phase14_records(base["scanner_results"], commit_sha=SHA)
             if record["scanner"] == "semgrep")
assert normalize_record(proof, expected_sha=SHA)["status"] == "completed"
for field, invalid in (("artifact_sha256", None), ("capture_complete", False), ("commit_sha", "b" * 40)):
    damaged = {**proof, field: invalid}
    try:
        normalize_record(damaged, expected_sha=SHA)
    except AnalyzerEvidenceError:
        pass
    else:
        raise AssertionError(f"Invalid retained capture accepted: {field}")
if language == "python":
    # Preserve the original minimal failure as a negative control: identical
    # source/version and completion claims, but no retained capture proof.
    damaged_package = deepcopy(package)
    for record in damaged_package["json"]["scanner_execution_records"]:
        if record.get("completed") is True:
            record.pop("artifact_sha256", None)
            record["capture_complete"] = False
    constrained = rebuild_client_artifacts(damaged_package)["json"]
    expected = (observations["clean"][0], observations["clean"][0] - 12)
    assert scores({"assessment": constrained["assessment"]}) == expected
    print(json.dumps({"missing_capture_negative_control": {
        "source_sha": SHA, "scoring_version": scoring.VERSION,
        "before": observations["clean"], "after": expected,
    }}), flush=True)
source = rebuild_client_artifacts(package)
truth = source["json"]
assert scores({"assessment": truth["assessment"]}) == observations["clean"], {
    "stage": "artifact_rebuild", "expected": observations["clean"],
    "actual": scores({"assessment": truth["assessment"]}),
    "contract": truth["assessment"].get("score_contract"),
    "coverage": truth["assessment"].get("evidence_coverage"),
}
source["report_id"] = truth.get("report_id") or "comprehensive_report_owned_scoring_probe"
source["canonical_truth_sha256"] = locale.canonical_sha256(truth)
status = {key: truth["identity"][key] for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")}
status.update(report_language="en", terminal=True, reports=source)
before = deepcopy(status)
localized = locale.build_same_run_locale_report(status, "es-MX")
assert status == before
assert localized["report"]["json"] == truth
spanish = localized["report"]["localized_artifact_json"]
assert scores({"assessment": spanish["assessment"]}) == observations["clean"]
assert spanish["assessment"]["score_contract"]["version"] == scoring.VERSION
assert spanish["identity"]["commit_sha"] == SHA
assert spanish["identity"]["evidence_ledger_id"] == context["evidence_ledger_id"]
record = _record_with_canonical_final_report()
record["identity"].update(truth["identity"])
record["stage_results"][FINAL_STAGE].update(report_package=source, assessment=truth["assessment"])
record_before = deepcopy(record)
client = TestClient(_app(record))
for _ in range(2):
    response = client.get(f"/assessment/comprehensive-run/{RUN_ID}/report/json")
    assert response.status_code == 200, response.text[:1000]
    returned = response.json()
    assert scores({"assessment": returned["assessment"]}) == observations["clean"]
    assert returned["identity"]["commit_sha"] == SHA
    assert returned["identity"]["repository"] == context["repository"]
    assert returned["assessment"]["score_contract"]["version"] == scoring.VERSION
assert record == record_before
print(json.dumps({"real_artifacts_and_api": "passed", "scores": observations["clean"],
                  "canonical_truth_sha256": source["canonical_truth_sha256"],
                  "english_pdf_sha256": source["pdf_sha256"],
                  "spanish_pdf_sha256": localized["report"]["pdf_sha256"]}), flush=True)
