"""Offline measurements only. No assessment execution or approval authority."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import stat

EXPECTED = "nico.shadow-expected.v1"
OBSERVED = "nico.shadow-observed.v1"
RESULT = "nico.shadow-result.v1"
CONTRACT = "nico.candidate-technical-triage.v2"
MAX_BYTES = 2 * 1024 * 1024
LABELS = {"confirmed", "not_actionable", "needs_review"}
BOUNDARIES = {
    "shadow_only": True, "human_review_required": True,
    "client_delivery_blocked": True, "approved": False,
    "autonomy_qualified": False, "score_effect": "none",
}
LIMITATIONS = [
    "Test labels are supplied expectations, not reviewer identities or specialist evidence.",
    "No production calibration, approval, delivery, or acceptable false-negative threshold.",
    "Only supplied corpus membership and candidate-to-finding mappings are measured; oracle completeness is not proven.",
    "No evidence validity, severity, remediation, report quality, or METRICS.md target qualification is measured.",
    "Checksums bind supplied bytes, not their authenticity; no source or assessment is executed.",
]


class Invalid(ValueError):
    """An input contract violation; message is a fixed code, never input content."""


def require(condition, code):
    if not condition:
        raise Invalid(code)


def obj(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()), "invalid_object_fields")


def token(value):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,199}", value), "invalid_identity")


def rows(value, key):
    require(type(value) is list and len(value) <= 10000, "invalid_rows")
    found = {}
    for row in value:
        require(type(row) is dict and key in row, "invalid_row")
        token(row[key])
        require(row[key] not in found, "duplicate_identity")
        found[row[key]] = row
    return found


def scope(value):
    obj(value, "source_id repository revision source_schema")
    for item in value.values():
        token(item)
    require(re.fullmatch(r"[0-9a-f]{40}", value["revision"]), "invalid_revision")
    require(value["source_schema"] == CONTRACT, "unsupported_source_schema")


def validate_expected(value):
    obj(value, "schema corpus_id corpus_version label_kind cases")
    require(value["schema"] == EXPECTED, "unsupported_expected_schema")
    require(value["label_kind"] == "test_expectations", "invalid_label_kind")
    token(value["corpus_id"])
    token(value["corpus_version"])
    cases = rows(value["cases"], "case_id")
    require(cases, "empty_corpus")
    for case in cases.values():
        obj(case, "case_id scope candidates material_findings")
        scope(case["scope"])
        candidates = rows(case["candidates"], "candidate_id")
        for row in candidates.values():
            obj(row, "candidate_id expected_verdict")
            require(row["expected_verdict"] in LABELS, "unknown_expected_label")
        findings = rows(case["material_findings"], "finding_id")
        assigned = set()
        for row in findings.values():
            obj(row, "finding_id candidate_ids")
            ids = row["candidate_ids"]
            require(type(ids) is list and len(ids) <= 10000, "invalid_finding_mapping")
            for candidate in ids:
                token(candidate)
                require(candidate in candidates and candidate not in assigned, "invalid_finding_mapping")
                require(candidates[candidate]["expected_verdict"] == "confirmed", "material_label_conflict")
                assigned.add(candidate)
        require(all(row["expected_verdict"] != "confirmed" or cid in assigned for cid, row in candidates.items()), "unmapped_material_candidate")
    return cases


def validate_observed(value, expected, digest):
    obj(value, "schema corpus_id corpus_version expected_sha256 cases")
    require(value["schema"] == OBSERVED, "unsupported_observed_schema")
    require(value["expected_sha256"] == digest, "stale_expected_answers")
    require(all(value[k] == expected[k] for k in ("corpus_id", "corpus_version")), "foreign_corpus")
    expected_cases = {c["case_id"]: c for c in expected["cases"]}
    cases = rows(value["cases"], "case_id")
    require(set(cases) <= set(expected_cases), "foreign_case")
    for cid, case in cases.items():
        obj(case, "case_id scope status findings")
        scope(case["scope"])
        require(case["scope"] == expected_cases[cid]["scope"], "foreign_scope")
        require(case["status"] in {"complete", "partial", "unavailable"}, "unknown_status")
        findings = rows(case["findings"], "candidate_id")
        require(case["status"] != "unavailable" or not findings, "unavailable_with_findings")
        candidates = {r["candidate_id"] for r in expected_cases[cid]["candidates"]}
        require(set(findings) <= candidates, "unmapped_candidate")
        for row in findings.values():
            obj(row, "candidate_id technical_triage_verdict")
            require(row["technical_triage_verdict"] in LABELS, "unknown_observed_label")
    return cases


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None,
            "unknown_reason": None if denominator else "zero_denominator"}


def compare(expected, observed, expected_digest):
    """Pure comparison; all aggregates are recomputed from individually bound rows."""
    cases = validate_expected(expected)
    observations = validate_observed(observed, expected, expected_digest)
    totals = Counter()
    results = []
    reasons = set()
    for cid, case in sorted(cases.items()):
        observation = observations.get(cid)
        status = observation["status"] if observation else "missing"
        totals["cases"] += 1
        totals["observed_cases"] += observation is not None
        totals["complete_cases"] += status == "complete"
        if status != "complete":
            reasons.add("incomplete_observations")
        totals["missing_cases"] += status == "missing"
        actual = {r["candidate_id"]: r["technical_triage_verdict"] for r in observation["findings"]} if observation else {}
        decisions = []
        for row in sorted(case["candidates"], key=lambda r: r["candidate_id"]):
            candidate = row["candidate_id"]
            truth, verdict = row["expected_verdict"], actual.get(candidate)
            totals["expected_candidates"] += 1
            totals["observed_candidates"] += verdict is not None
            totals["resolved_expected_candidates"] += truth != "needs_review"
            totals["unresolved_expected_candidates"] += truth == "needs_review"
            if truth == "needs_review":
                reasons.add("unresolved_expected_answers")
            if verdict is None:
                outcome = "missing_observation"
            elif verdict == "needs_review":
                outcome = "abstention"
            elif verdict == "not_actionable" and truth != "not_actionable":
                outcome = "unsafe_dismissal"
            elif verdict == "confirmed" and truth != "confirmed":
                outcome = "incorrect_confirmation" if truth == "not_actionable" else "unsupported_confirmation"
            else:
                outcome = "correct_result"
            totals[outcome] += 1
            totals["label_agreements"] += verdict == truth
            if outcome in {"unsafe_dismissal", "incorrect_confirmation", "unsupported_confirmation", "missing_observation"}:
                reasons.add(outcome)
            decisions.append({**row, "observed_verdict": verdict, "outcome": outcome})
        detected = []
        for finding in sorted(case["material_findings"], key=lambda r: r["finding_id"]):
            ids = finding["candidate_ids"]
            present = any(c in actual for c in ids)
            confirmed = any(actual.get(c) == "confirmed" for c in ids)
            totals["expected_material_findings"] += 1
            totals["detected_material_findings"] += present
            totals["confirmed_material_findings"] += confirmed
            totals["omitted_material_findings"] += not present
            totals["unresolved_material_findings"] += not confirmed
            if not confirmed:
                reasons.add("unresolved_material_findings")
            detected.append({**finding, "detected": present, "confirmed": confirmed,
                             "outcome": "confirmed" if confirmed else "unresolved" if present else "omitted_false_negative"})
        true_zero = not case["material_findings"] and not case["candidates"]
        totals["expected_true_zero_cases"] += true_zero
        totals["observed_true_zero_cases"] += true_zero and status == "complete"
        results.append({"case_id": cid, "scope": case["scope"], "status": status,
                        "candidates": decisions, "material_findings": detected})
    pairs = {
        "case_coverage": ("observed_cases", "cases"),
        "complete_case_coverage": ("complete_cases", "cases"),
        "candidate_coverage": ("observed_candidates", "expected_candidates"),
        "candidate_label_agreement": ("label_agreements", "expected_candidates"),
        "resolved_candidate_correctness": ("correct_result", "resolved_expected_candidates"),
        "abstention": ("abstention", "expected_candidates"),
        "material_detection": ("detected_material_findings", "expected_material_findings"),
        "material_confirmation": ("confirmed_material_findings", "expected_material_findings"),
        "material_omission": ("omitted_material_findings", "expected_material_findings"),
        "material_unresolved": ("unresolved_material_findings", "expected_material_findings"),
        "true_zero_coverage": ("observed_true_zero_cases", "expected_true_zero_cases"),
    }
    for name in ("incorrect_confirmation", "unsupported_confirmation", "unsafe_dismissal", "missing_observation"):
        pairs[name] = (name, "expected_candidates")
    metrics = {name: fraction(totals[n], totals[d]) for name, (n, d) in pairs.items()}
    reasons.update("zero_denominator:" + name for name, metric in metrics.items() if metric["denominator"] == 0)
    return {"measurement_status": "measured", "corpus_id": expected["corpus_id"],
            "corpus_version": expected["corpus_version"], "cases": results,
            "counts": dict(sorted(totals.items())), "metrics": metrics,
            "block_or_unknown_reasons": sorted(reasons | {"shadow_only_no_qualification"})}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path, *, dir_fd=None):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=dir_fd)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "input_not_regular_file")
        data = stream.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, "input_size_limit")
    return data


def parse(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Invalid("nonfinite_json")))


def evaluate_files(expected_path, observed_path, output_dir):
    """Retain bounded inputs verbatim in a NEW local directory, including invalid runs."""
    retained, errors = {}, []
    for name, path in (("expected", expected_path), ("observed", observed_path)):
        try:
            retained[name] = read_bounded(path)
        except (OSError, Invalid) as exc:
            errors.append(name + ":" + (str(exc) if isinstance(exc, Invalid) else "input_unreadable"))
    output = Path(output_dir)
    output.mkdir(mode=0o700)  # Refuse any existing destination; never overwrite inputs.
    evidence = {}
    for name, data in retained.items():
        filename = name + ".input.json"
        (output / filename).write_bytes(data)
        evidence[name] = {"path": filename, "sha256": digest(data), "bytes": len(data)}
    result = {"schema": RESULT, **BOUNDARIES, "limitations": LIMITATIONS,
              "inputs": evidence, "measurement_status": "invalid",
              "metrics": None, "cases": [], "block_or_unknown_reasons": errors}
    if "expected" in retained:
        try:
            expected = parse(retained["expected"])
            # Preserve all expected rows even when observation validation fails.
            validate_expected(expected)
            result["cases"] = expected["cases"]
            if not errors:
                result.update(compare(expected, parse(retained["observed"]), digest(retained["expected"])))
        except (Invalid, ValueError, TypeError, RecursionError) as exc:
            result["block_or_unknown_reasons"] = errors + [str(exc) if isinstance(exc, Invalid) else "malformed_input"]
    serialized = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    (output / "result.json").write_bytes(serialized)
    (output / "checksums.json").write_text(json.dumps({
        **{item["path"]: item["sha256"] for item in evidence.values()},
        "result.json": digest(serialized),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--observed", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = evaluate_files(args.expected, args.observed, args.output)
    except (OSError, Invalid):
        parser.exit(2, "Cannot create new local evidence directory or retain evidence.\n")
    print(result["measurement_status"] + "; shadow only; human review required; client delivery blocked")
    return 0 if result["measurement_status"] == "measured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
