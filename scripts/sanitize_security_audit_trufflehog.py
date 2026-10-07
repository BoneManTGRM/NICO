"""Retain TruffleHog observations without publishing candidate credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FINDING_SCHEMA = "nico.security-audit.trufflehog.finding.v1"
CAPTURE_SCHEMA = "nico.security-audit.trufflehog.capture.v1"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _safe_finding(value):
    if not isinstance(value, dict):
        raise ValueError("finding is not an object")
    raw, detector, verified = value.get("Raw"), value.get("DetectorName"), value.get("Verified")
    if not isinstance(raw, str) or not isinstance(detector, str) or not isinstance(verified, bool):
        raise ValueError("finding fields have invalid types")
    source = value.get("SourceMetadata")
    data = source.get("Data") if isinstance(source, dict) else None
    git = data.get("Git") if isinstance(data, dict) else None
    safe_git = {}
    if isinstance(git, dict):
        for key in ("file", "commit"):
            if isinstance(git.get(key), str):
                safe_git[key] = git[key]
        if type(git.get("line")) is int:
            safe_git["line"] = git["line"]
    result = {
        "SanitizationSchema": FINDING_SCHEMA,
        "DetectorName": detector,
        "Verified": verified,
        "RawSHA256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "SourceMetadata": {"Data": {"Git": safe_git}},
    }
    if type(value.get("DetectorType")) is int:
        result["DetectorType"] = value["DetectorType"]
    return result


def capture(input_path: Path, stderr_path: Path, exit_code: int, output_dir: Path):
    findings, invalid_lines = [], 0
    raw_digest = hashlib.sha256()
    input_present = input_path.is_file()
    if input_present:
        with input_path.open("rb") as stream:
            for line in stream:
                raw_digest.update(line)
                if not line.strip():
                    continue
                try:
                    findings.append(_safe_finding(json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)))
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    invalid_lines += 1
    sanitized = "".join(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n" for row in findings).encode()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "trufflehog.json").write_bytes(sanitized)
    stderr_digest, stderr_bytes = hashlib.sha256(), 0
    if stderr_path.is_file():
        with stderr_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                stderr_digest.update(chunk)
                stderr_bytes += len(chunk)
    (output_dir / "trufflehog.stderr.txt").write_text(json.dumps({
        "body_retained": False, "bytes": stderr_bytes, "sha256": stderr_digest.hexdigest(),
    }, sort_keys=True) + "\n")
    complete = input_present and invalid_lines == 0 and exit_code in {0, 183}
    summary = {
        "schema": CAPTURE_SCHEMA, "scanner": "trufflehog",
        "status": "completed" if complete else "unavailable",
        "finding_count": len(findings), "artifact_present": input_present,
        "history_depth": "full", "exit_code": exit_code,
        "invalid_json_lines": invalid_lines, "live_credential_verification": False,
        "raw_capture_sha256": raw_digest.hexdigest() if input_present else None,
        "sanitized_artifact_sha256": hashlib.sha256(sanitized).hexdigest(),
        "raw_candidate_bodies_retained": False,
    }
    (output_dir / "trufflehog-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    capture(args.input, args.stderr, args.exit_code, args.output_dir)


if __name__ == "__main__":
    main()
