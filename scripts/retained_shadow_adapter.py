"""Project explicitly selected retained registers into shadow observations, offline."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path

import offline_shadow_evaluation as shadow

SELECTION = "nico.shadow-selection.v1"
RESULT = "nico.shadow-adapter-result.v1"
REGISTER = "nico.canonical-scanner-findings.v1"
MAX_RECORDS = 32
LIMITATIONS = shadow.LIMITATIONS + [
    "Supplied source identity and hashes bind bytes, not authenticity or oracle completeness.",
    "Register projection is always partial; no complete-assessment or true-zero claim.",
    "Comparator detection counts verdict-bearing candidates only; separate retained candidate presence is reported here.",
    "No inference, revalidation, approval, reviewer identity, or disposition is created.",
]


@contextmanager
def parent_fd(path):
    """Walk directories without following symlinks, then anchor subsequent I/O."""
    path = Path(path)
    shadow.require(path.name not in {"", ".", ".."} and ".." not in path.parts,
                   "unsafe_path")
    fd = os.open("/" if path.is_absolute() else ".", os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = path.parts[1:-1] if path.is_absolute() else path.parts[:-1]
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, path.name
    finally:
        os.close(fd)


def read(path):
    with parent_fd(path) as (fd, name):
        # Same bounded regular-file reader as the comparator, with anchored parent.
        return shadow.read_bounded(name, dir_fd=fd)


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def project(expected, selection, registers, expected_hash):
    cases = shadow.validate_expected(expected)
    shadow.obj(selection, "schema expected_sha256 cases")
    shadow.require(selection["schema"] == SELECTION, "unsupported_selection_schema")
    shadow.require(selection["expected_sha256"] == expected_hash, "stale_expected_answers")
    selected = shadow.rows(selection["cases"], "case_id")
    shadow.require(len(selected) <= MAX_RECORDS, "too_many_records")
    shadow.require(set(selected) == set(registers), "selection_file_mismatch")
    shadow.require(set(selected) <= set(cases), "foreign_case")
    observed = {"schema": shadow.OBSERVED, "corpus_id": expected["corpus_id"],
                "corpus_version": expected["corpus_version"],
                "expected_sha256": expected_hash, "cases": []}
    details, identities = [], set()
    for cid, entry in sorted(selected.items()):
        shadow.obj(entry, "case_id scope register_sha256")
        shadow.scope(entry["scope"])
        scope = entry["scope"]
        shadow.require(scope == cases[cid]["scope"], "foreign_scope")
        identity = tuple(scope[k] for k in sorted(scope))
        shadow.require(identity not in identities, "duplicate_source_identity")
        identities.add(identity)
        raw = registers[cid]
        shadow.require(entry["register_sha256"] == shadow.digest(raw), "register_checksum_mismatch")
        register = shadow.parse(raw)
        shadow.require(type(register) is dict, "invalid_register")
        shadow.require(register.get("artifact_schema") == REGISTER, "unsupported_register_schema")
        shadow.require(register.get("exact_commit_sha") == scope["revision"], "foreign_revision")
        subject = register.get("assessment_subject")
        shadow.require(type(subject) is dict and subject.get("repository") == scope["repository"],
                       "foreign_or_missing_repository")
        triage = register.get("technical_triage")
        shadow.require(type(triage) is dict and triage.get("artifact_schema") == shadow.CONTRACT,
                       "unsupported_triage_schema")
        # Nested source_target_commit_sha denotes prior lineage, NOT current scope.
        records = shadow.rows(register.get("findings"), "candidate_id")
        known = {r["candidate_id"] for r in cases[cid]["candidates"]}
        shadow.require(set(records) <= known, "unmapped_candidate")
        findings, missing = [], []
        for candidate_id, row in sorted(records.items()):
            if "exact_commit_sha" in row:
                shadow.require(row["exact_commit_sha"] == scope["revision"], "foreign_candidate_revision")
            if "technical_triage_verdict" not in row or row["technical_triage_verdict"] is None:
                missing.append(candidate_id)
                continue
            verdict = row["technical_triage_verdict"]
            shadow.require(type(verdict) is str and verdict in shadow.LABELS, "unknown_observed_label")
            findings.append({"candidate_id": candidate_id, "technical_triage_verdict": verdict})
        observed["cases"].append({"case_id": cid, "scope": scope, "status": "partial", "findings": findings})
        details.append({"case_id": cid, "retained_candidate_ids": sorted(records),
                        "missing_verdict_candidate_ids": missing,
                        "absent_expected_candidate_ids": sorted(known - set(records)),
                        "retained_records": len(records), "verdicts_transcribed": len(findings)})
    comparison = shadow.compare(expected, observed, expected_hash)
    return observed, comparison, details


def run(expected_path, selection_path, record_paths, output_path):
    shadow.require(len(record_paths) <= MAX_RECORDS, "too_many_records")
    ids = [cid for cid, _ in record_paths]
    for cid in ids:
        shadow.token(cid)
    shadow.require(len(ids) == len(set(ids)), "duplicate_record_selection")
    retained, errors = {}, []
    paths = [("expected", expected_path), ("selection", selection_path)]
    paths += [(f"record-{i:02d}", path) for i, (_, path) in enumerate(record_paths)]
    for name, path in paths:
        try:
            retained[name] = read(path)
        except (OSError, shadow.Invalid) as exc:
            errors.append(name + ":" + (str(exc) if isinstance(exc, shadow.Invalid) else "input_unreadable"))
    result = {"schema": RESULT, **shadow.BOUNDARIES, "limitations": LIMITATIONS,
              "status": "invalid", "errors": errors, "expected_cases": [],
              "selected_file_count": len(record_paths), "records_handled": None,
              "verdicts_transcribed": None, "cases": [], "inputs": {},
              "record_bindings": [{"case_id": cid, "input": f"record-{i:02d}.input.json"}
                                  for i, (cid, _) in enumerate(record_paths)]}
    generated = {}
    try:
        if "expected" in retained:
            expected = shadow.parse(retained["expected"])
            shadow.validate_expected(expected)
            result["expected_cases"] = expected["cases"]
        if not errors:
            registers = {cid: retained[f"record-{i:02d}"] for i, (cid, _) in enumerate(record_paths)}
            observed, comparison, details = project(expected, shadow.parse(retained["selection"]),
                                                    registers, shadow.digest(retained["expected"]))
            result.update(status="projected", cases=details,
                          records_handled=sum(c["retained_records"] for c in details),
                          verdicts_transcribed=sum(c["verdicts_transcribed"] for c in details))
            generated["observed.json"] = encode(observed)
            generated["comparison.json"] = encode({"schema": shadow.RESULT, **shadow.BOUNDARIES,
                                                   "limitations": LIMITATIONS, **comparison})
    except (shadow.Invalid, ValueError, TypeError, RecursionError) as exc:
        result["errors"].append(str(exc) if isinstance(exc, shadow.Invalid) else "malformed_input")
    for name, raw in retained.items():
        filename = name + ".input.json"
        generated[filename] = raw
        result["inputs"][name] = {"path": filename, "sha256": shadow.digest(raw), "bytes": len(raw)}
    generated["adapter-result.json"] = encode(result)
    generated["checksums.json"] = encode({name: shadow.digest(raw) for name, raw in sorted(generated.items())})
    with parent_fd(output_path) as (parent, name):
        os.mkdir(name, mode=0o700, dir_fd=parent)  # Existing paths are never overwritten.
        out = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            for filename, raw in generated.items():
                fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=out)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
        finally:
            os.close(out)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--record", nargs=2, action="append", default=[], metavar=("CASE_ID", "PATH"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.expected, args.selection, args.record, args.output)
    except (OSError, shadow.Invalid):
        parser.exit(2, "Cannot retain evidence or invalid explicit file selection.\n")
    print(result["status"] + "; shadow only; human review required; client delivery blocked")
    return 0 if result["status"] == "projected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
