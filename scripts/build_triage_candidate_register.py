#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from triage662_core import (EXPECTED, dependency_candidates, read_json, repo_path,
                            static_candidates, validate_run)
from triage662_secrets import secret_candidates


def build(run: dict[str, Any], sha: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    secrets, excluded = secret_candidates(run, sha)
    rows = sorted([*static_candidates(run, sha), *dependency_candidates(run, sha), *secrets],
                  key=lambda item: (item["category"], item["scanner"], item["candidate_id"]))
    counts = Counter(item["category"] for item in rows)
    ids = [item["candidate_id"] for item in rows]
    if dict(counts) != EXPECTED or len(rows) != 662 or len(ids) != len(set(ids)):
        raise ValueError(f"Candidate register failed reconciliation: count={len(rows)}, categories={dict(counts)}")
    return rows, sorted(excluded, key=lambda item: item["exclusion_id"])


def csv_text(rows: list[dict[str, Any]]) -> str:
    fields = ["candidate_id", "cluster_id", "category", "scanner", "rule_id", "title", "path", "line",
              "history_commit", "package", "installed_version", "ecosystem", "severity", "confidence", "verified",
              "evidence_scope", "proposed_disposition", "rationale", "confirmed_material", "human_review_required",
              "human_approved", "source_evidence_fingerprint", "target_commit_sha"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def write_package(output: Path, repository: str, sha: str, proof: dict[str, Any], run_ids: list[str],
                  raw_count: int, rows: list[dict[str, Any]], excluded: list[dict[str, Any]]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    counts = Counter(item["category"] for item in rows)
    dispositions = Counter(item["proposed_disposition"] for item in rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["cluster_id"]].append(row)
    clusters = [{"cluster_id": key, "category": values[0]["category"], "scanner": values[0]["scanner"],
                 "rule_id": values[0]["rule_id"], "candidate_count": len(values),
                 "proposed_dispositions": sorted({item["proposed_disposition"] for item in values}),
                 "human_review_required": True, "human_approved": False}
                for key, values in sorted(grouped.items())]
    reconciliation = {
        "schema": "nico.triage_candidate_reconciliation.v1", "repository": repository,
        "target_commit_sha": sha, "raw_nonzero_observation_count": raw_count,
        "canonical_candidate_count": len(rows), "canonical_counts": dict(sorted(counts.items())),
        "excluded_observation_count": len(excluded), "excluded_observations": excluded,
        "reconciliation_complete": len(rows) == 662 and len(rows) + len(excluded) == raw_count,
        "no_silent_deletion": True, "secret_material_omitted": True,
    }
    register = {
        "schema": "nico.triage_candidate_register.v1", "repository": repository, "target_commit_sha": sha,
        "automated_status": "automated_draft", "human_review_status": "pending",
        "client_delivery_status": "blocked", "confirmed_material_findings": 0,
        "candidate_count": len(rows), "counts": dict(sorted(counts.items())),
        "proposed_disposition_counts": dict(sorted(dispositions.items())), "two_run_parity_verified": True,
        "scanner_proof_schema": proof.get("schema"), "source_run_ids": run_ids,
        "secret_material_omitted": True, "candidates": rows,
    }
    exclusions = Counter(item["reason"] for item in excluded)
    report = f"""# NICO Comprehensive Candidate-Triage Report

**AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED**

- Repository: `{repository}`
- Exact assessed commit: `{sha}`
- Evidence basis: two deterministic scanner passes over the exact assessed commit
- Canonical candidate population: **{len(rows)}**
- Confirmed material findings: **0 before authorized human review**
- Human approval: **not granted**

## Reconciliation

| Category | Canonical candidates |
|---|---:|
| Static | {counts['static']} |
| Dependency | {counts['dependency']} |
| Secret | {counts['secret']} |
| **Total** | **{len(rows)}** |

The two scanner passes produced {raw_count} raw nonzero observations. The canonical register contains 662 candidates after retaining one record for each of four exact duplicate TruffleHog observations and recording one unverified `.env.example` template observation in the exclusion ledger. Nothing is silently deleted.

## Proposed dispositions

| Proposed disposition | Count |
|---|---:|
""" + "\n".join(f"| `{name}` | {count} |" for name, count in sorted(dispositions.items())) + """

All dispositions are proposals. None constitutes human approval, risk acceptance, or confirmation that a candidate is exploitable or harmless.

## Excluded-observation ledger

| Reason | Count |
|---|---:|
""" + "\n".join(f"| `{name}` | {count} |" for name, count in sorted(exclusions.items())) + f"""

## Integrity controls

- Stable unique candidate identities: **{len({item['candidate_id'] for item in rows}) == len(rows)}**
- Stable cluster identities: **{len(clusters)} clusters**
- Two-run candidate parity: **verified**
- Raw secret material in register and report: **omitted**
- Client delivery: **blocked pending authorized human review**

The complete candidate records are retained in `candidate-register.json` and `candidate-register.csv`; cluster mappings are in `candidate-clusters.json`.
"""
    files = {
        "candidate-register.json": (json.dumps(register, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(),
        "candidate-register.csv": csv_text(rows).encode(),
        "candidate-clusters.json": (json.dumps(clusters, indent=2, sort_keys=True) + "\n").encode(),
        "reconciliation.json": (json.dumps(reconciliation, indent=2, sort_keys=True) + "\n").encode(),
        "comprehensive-triage-report.md": report.encode(),
    }
    manifest = {
        "schema": "nico.triage_candidate_package_manifest.v1", "repository": repository,
        "target_commit_sha": sha, "candidate_count": len(rows), "counts": dict(sorted(counts.items())),
        "excluded_observation_count": len(excluded), "raw_nonzero_observation_count": raw_count,
        "source_run_ids": run_ids, "two_run_parity_verified": True, "automated_status": "automated_draft",
        "human_review_status": "pending", "client_delivery_status": "blocked",
        "artifacts": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    for name, data in files.items():
        (output / name).write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scanner-run-one", type=Path, required=True)
    parser.add_argument("--scanner-run-two", type=Path, required=True)
    parser.add_argument("--scanner-proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", default="BoneManTGRM/NICO")
    args = parser.parse_args()
    first, second, proof = map(read_json, (args.scanner_run_one, args.scanner_run_two, args.scanner_proof))
    sha = validate_run(first)
    validate_run(second, sha)
    if proof.get("target_commit_sha") != sha or proof.get("two_consecutive_clean_runs") is not True or (proof.get("comparison") or {}).get("equivalent") is not True:
        raise ValueError("Two-pass exact-SHA proof is incomplete.")
    rows1, excluded1 = build(first, sha)
    rows2, excluded2 = build(second, sha)
    if json.dumps(rows1, sort_keys=True) != json.dumps(rows2, sort_keys=True) or json.dumps(excluded1, sort_keys=True) != json.dumps(excluded2, sort_keys=True):
        raise ValueError("Candidate register differs between scanner runs.")
    tools = ("bandit", "osv-scanner", "gitleaks", "trufflehog")
    raw1 = sum(int((((first.get("tools") or {}).get(tool) or {}).get("findings_count") or 0)) for tool in tools)
    raw2 = sum(int((((second.get("tools") or {}).get(tool) or {}).get("findings_count") or 0)) for tool in tools)
    if raw1 != raw2 or len(rows1) + len(excluded1) != raw1:
        raise ValueError(f"Raw/canonical reconciliation failed: raw={raw1}/{raw2}, canonical={len(rows1)}, excluded={len(excluded1)}")
    write_package(args.output, args.repository, sha, proof,
                  [str(first.get("run_id") or ""), str(second.get("run_id") or "")],
                  raw1, rows1, excluded1)
    print(json.dumps({"status": "complete", "candidate_count": len(rows1),
                      "counts": dict(Counter(item["category"] for item in rows1)),
                      "excluded_observation_count": len(excluded1),
                      "client_delivery_status": "blocked"}, indent=2, sort_keys=True))
    return 0


_normal_path = repo_path
_secret_candidates = secret_candidates

if __name__ == "__main__":
    raise SystemExit(main())
