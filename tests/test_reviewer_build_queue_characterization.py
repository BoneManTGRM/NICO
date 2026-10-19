"""Full models and thrown errors captured on 66a2320b before extraction."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.test_reviewer_queue_producer_consumer_routing import _payload, ROOT
from nico.candidate_phase1_workload_refinement_v1 import refine_candidate_review_workload


def cases():
    output = {"valid": _payload(), "missing_register": {}, "null_payload": None}
    for field in ("findings", "review_workload_clusters", "technical_triage", "candidate_record_count"):
        for value in (None, [], {}, "bad", 0):
            payload = _payload()
            payload["candidate_register"][field] = value
            output[f"register:{field}:{json.dumps(value)}"] = payload
    for field in ("candidate_count", "human_review_work_units", "scanner_candidate_review_work_units",
                  "exact_source_review_work_units", "operational_context_review_work_units",
                  "total_unresolved_human_review_work_units", "operator_attention_required"):
        for value in (None, "", "0", 0, -1, False):
            payload = _payload()
            payload[field] = value
            output[f"payload:{field}:{json.dumps(value)}"] = payload
    for field in ("total_candidates", "cluster_count", "grouped_review_cluster_count",
                  "candidates_eligible_for_grouped_review", "grouped_human_review_candidate_count",
                  "candidates_requiring_individual_human_attention", "individual_human_review_record_count",
                  "human_review_work_units", "review_workload_clusters"):
        payload = _payload()
        payload["candidate_register"]["technical_triage"][field] = None
        output[f"triage:{field}"] = payload
    for field, value in (("candidate_id", ""), ("candidate_id", "human-a"),
                         ("review_routing_class", "UNKNOWN"), ("review_requires_individual_attention", False),
                         ("exact_commit_sha", "b" * 40), ("human_review_required", False),
                         ("client_delivery_allowed", True), ("human_disposition", "accepted")):
        payload = _payload()
        payload["candidate_register"]["findings"][0][field] = value
        output[f"candidate:{field}:{value}"] = payload
    for field in ("exact_source_review_findings", "operational_context_review_findings"):
        payload = _payload()
        payload[field] = [None, [], {}, {"finding_id": "extra"}, "bad"]
        output[f"mixed:{field}"] = payload
    for mode in ("reverse", "ties", "priorities", "duplicate_last_wins", "filtered_findings", "multiple_errors"):
        payload = _payload()
        register = payload["candidate_register"]
        if mode in ("reverse", "ties", "priorities"):
            register["findings"].reverse()
            register["review_workload_clusters"].reverse()
            register["technical_triage"]["review_workload_clusters"] = deepcopy(register["review_workload_clusters"])
            for i, candidate in enumerate(register["findings"]):
                if mode == "ties":
                    candidate.update(severity="low", category="static")
                elif mode == "priorities":
                    candidate.update(severity=("critical", "HIGH", "moderate", "unknown")[i % 4],
                                     category=("secret", "dependency", "static", "unknown")[i % 4])
        elif mode == "duplicate_last_wins":
            register["findings"].append({**register["findings"][0], "severity": "low", "retained_marker": "last"})
        elif mode == "filtered_findings":
            register["findings"] += [None, [], "bad", {}, {}]
        else:
            for candidate in register["findings"]:
                candidate.update(exact_commit_sha="wrong", human_review_required=False, human_disposition="accepted")
            payload.update(candidate_count=-1, operator_attention_required=False, total_unresolved_human_review_work_units=99)
        output[mode] = payload
    for mode in ("forward", "reverse", "equal_priority"):
        payload = _payload()
        findings = payload["candidate_register"]["findings"]
        for i in range(8):
            findings.append({**findings[0], "candidate_id": f"ordered-{i}",
                "severity": "low" if mode == "equal_priority" else ("critical", "high", "medium", "low")[i % 4],
                "category": "static" if mode == "equal_priority" else ("secret", "dependency", "static")[i % 3]})
        if mode != "forward":
            findings.reverse()
        register = refine_candidate_review_workload({"findings": findings, "candidate_record_count": len(findings),
            "technical_triage": {"total_candidates": len(findings)}})
        count = register["technical_triage"]["human_review_work_units"]
        payload.update(candidate_register=register, candidate_count=len(findings),
            human_review_work_units=count, scanner_candidate_review_work_units=count,
            total_unresolved_human_review_work_units=count + 1)
        output[f"many_units:{mode}"] = payload
    return output


CASES = cases()


def outcomes():
    script = r"""
const fs = require('node:fs'), vm = require('node:vm');
const {stripTypeScriptTypes, createRequire} = require('node:module');
const source = fs.readFileSync(process.argv[1], 'utf8');
const logic = source.slice(source.indexOf('type JsonRecord'), source.indexOf('function evidenceLabel'));
const appRequire = createRequire(require('node:path').resolve('apps/web/package.json'));
const compiled = stripTypeScriptTypes ? stripTypeScriptTypes(logic)
  : appRequire('typescript').transpileModule(logic, {compilerOptions: {target: 7}}).outputText;
const cases = JSON.parse(fs.readFileSync(0, 'utf8')), output = {};
for (const locale of ['en', 'es-MX']) {
  output[locale] = {};
  for (const [name, payload] of Object.entries(cases)) {
    const before = JSON.stringify(payload), scope = {payload, locale, outcome: null};
    vm.runInNewContext(compiled + '\ntry { outcome = {model: buildQueue(payload, locale)}; } catch (error) { outcome = {error: {name: error.name, message: error.message}}; }', scope);
    if (JSON.stringify(payload) !== before) throw new Error('Input mutation: ' + name);
    output[locale][name] = scope.outcome;
  }
}
process.stdout.write(JSON.stringify(output));
"""
    result = subprocess.run([shutil.which("node") or "node", "-e", script,
        str(ROOT / "apps/web/app/operations/reviewer-queue/ReviewerQueue.tsx")],
        input=json.dumps(CASES), text=True, capture_output=True, check=True, cwd=ROOT)
    return json.loads(result.stdout)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@pytest.fixture(scope="module")
def actual():
    return outcomes()


@pytest.mark.parametrize("locale", ["en", "es-MX"])
@pytest.mark.parametrize("case", CASES)
def test_complete_queue_model_and_errors_match_baseline(actual, locale, case):
    expected = json.loads(Path(__file__).with_suffix(".json").read_text())
    assert fingerprint(actual[locale][case]) == expected[locale][case]
