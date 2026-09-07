"""Exercise the real Python workload producer against the UI's TypeScript consumer."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from nico.candidate_phase1_workload_refinement_v1 import refine_candidate_review_workload


ROOT = Path(__file__).resolve().parents[1]


def _payload():
    records = []
    for identity, route, grouped in [
        ("individual", "CRITICAL_ATTENTION", False),
        ("human-a", "HUMAN_TECHNICAL_REVIEW", True),
        ("human-b", "HUMAN_TECHNICAL_REVIEW", True),
        ("qc-single", "QUALITY_CONTROL_ELIGIBLE", False),
        ("qc-a", "QUALITY_CONTROL_ELIGIBLE", True),
        ("qc-b", "QUALITY_CONTROL_ELIGIBLE", True),
        ("automated", "AUTOMATED_TRIAGE_COMPLETE", False),
        ("stable", "STABLE_CARRY_FORWARD", False),
    ]:
        human = route in {"CRITICAL_ATTENTION", "HUMAN_TECHNICAL_REVIEW"}
        records.append({
            "candidate_id": identity, "exact_commit_sha": "a" * 40,
            "category": "static", "scanner": "semgrep", "rule": "synthetic-rule",
            "severity": "high" if route == "CRITICAL_ATTENTION" else "low",
            "technical_triage_verdict": "needs_review" if human else "not_actionable",
            "technical_triage_confidence": "medium" if human else "high",
            "technical_triage_proof_gaps": ["reachability"] if human else [],
            "review_routing_class": route, "evidence_changed": not grouped,
            "human_review_required": True, "client_delivery_allowed": False,
            "human_disposition": None,
        })
    register = refine_candidate_review_workload({
        "findings": records, "candidate_record_count": 8,
        "technical_triage": {"total_candidates": 8},
    })
    return {
        "commit_sha": "a" * 40, "candidate_register": register, "candidate_count": 8,
        "human_review_work_units": 2, "scanner_candidate_review_work_units": 2,
        "exact_source_review_work_units": 1, "exact_source_review_findings": [{"finding_id": "source"}],
        "operational_context_review_work_units": 0, "operational_context_review_findings": [],
        "total_unresolved_human_review_work_units": 3, "operator_attention_required": True,
    }


def _consume(payload, locale="en"):
    # Execute the unchanged consumer without React/browser mocks. Node 20 CI uses
    # the application's installed TypeScript compiler; Node 24 can strip types.
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const {stripTypeScriptTypes, createRequire} = require('node:module');
const source = fs.readFileSync(process.argv[1], 'utf8');
const logic = source.slice(source.indexOf('type JsonRecord'), source.indexOf('function evidenceLabel'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const scope = {input};
const appRequire = createRequire(require('node:path').resolve('apps/web/package.json'));
const compiled = stripTypeScriptTypes ? stripTypeScriptTypes(logic)
  : appRequire('typescript').transpileModule(logic, {compilerOptions: {target: 7}}).outputText;
vm.runInNewContext(compiled + '\noutput = buildQueue(input.payload, input.locale)', scope);
process.stdout.write(JSON.stringify(scope.output));
"""
    result = subprocess.run(
        [shutil.which("node") or "node", "-e", script,
         str(ROOT / "apps/web/app/operations/reviewer-queue/ReviewerQueue.tsx")],
        input=json.dumps({"payload": payload, "locale": locale}), text=True, capture_output=True,
        check=True, cwd=ROOT,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("locale", ["en", "es-MX"])
def test_qc_and_automated_clusters_remain_accessible_without_inflating_human_work(locale):
    # Defect: treating every retained cluster as a human work unit hides the entire UI.
    model = _consume(_payload(), locale)
    assert model["integrityErrors"] == []
    assert len(model["individualUnits"]) == 1
    assert len(model["groupedUnits"]) == 1
    assert len(model["retainedUnits"]) == 4
    assert model["scannerCandidateReviewWorkUnits"] == 2
    assert model["totalUnresolvedHumanReviewWorkUnits"] == 3
    displayed = [candidate["candidate_id"] for unit in model["units"] + model["retainedUnits"] for candidate in unit["candidates"]]
    assert sorted(displayed) == ["automated", "human-a", "human-b", "individual", "qc-a", "qc-b", "qc-single", "stable"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "routing", "attention", "group-human", "workload"])
def test_tampered_candidate_and_workload_evidence_still_fails_closed(mutation):
    payload = deepcopy(_payload())
    register = payload["candidate_register"]
    if mutation == "missing":
        register["findings"].pop()
    elif mutation == "duplicate":
        register["findings"][1]["candidate_id"] = register["findings"][0]["candidate_id"]
    elif mutation == "unknown":
        register["review_workload_clusters"][0]["candidate_ids"][0] = "not-retained"
    elif mutation == "routing":
        register["findings"][0]["review_routing_class"] = "invented-route"
    elif mutation == "attention":
        register["findings"][0]["review_requires_individual_attention"] = False
    elif mutation == "group-human":
        cluster = next(item for item in register["review_workload_clusters"] if item["grouped_human_review_cluster"])
        cluster["grouped_human_review_cluster"] = False
    elif mutation == "workload":
        payload["scanner_candidate_review_work_units"] = 0
    assert _consume(payload)["integrityErrors"]
