"""Read one blocked synthetic run without executing, reviewing or publishing it.

Only codes and error fragments present literally in the checked-out source are
retained. Dynamic exception content, tokens and complete run bodies are not saved.
A successful diagnostic is never a production acceptance result.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any

import httpx

ORIGIN = "https://app.nicoaudit.com"
_RUN = re.compile(r"comprun_[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CODE = re.compile(r"[a-z][a-z0-9_]{2,100}\Z")
STAGE = "final_comprehensive_report_generation"


def source_catalog(directory: Path) -> tuple[set[str], list[tuple[str, int, str]]]:
    """Parse trusted source; never import or execute it to classify a message."""
    codes: set[str] = set()
    fragments: list[tuple[str, int, str]] = []
    for path in sorted(directory.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _CODE.fullmatch(node.value):
                    codes.add(node.value)
            if not isinstance(node, ast.Raise):
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Constant) or not isinstance(child.value, str):
                    continue
                text = child.value
                if 20 <= len(text) <= 200 and text.isprintable():
                    fragments.append((path.name, child.lineno, text))
    return codes, sorted(set(fragments), key=lambda item: (-len(item[2]), item[0], item[1]))


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def diagnose(*, client: Any, run_id: str, expected_commit: str,
             codes: set[str], fragments: list[tuple[str, int, str]]) -> dict[str, Any]:
    if not _RUN.fullmatch(run_id) or not _SHA.fullmatch(expected_commit):
        raise ValueError("diagnostic_identity_invalid")
    with client.stream("GET", f"{ORIGIN}/api/nico/assessment/comprehensive-run/{run_id}",
                       follow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError(f"diagnostic_http_{response.status_code}")
        raw = bytearray()
        deadline = time.monotonic() + 20
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 250_000 or time.monotonic() > deadline:
                raise ValueError("diagnostic_response_limit")
    value = _mapping(json.loads(raw))
    if value.get("run_id") != run_id or value.get("commit_sha") != expected_commit:
        raise ValueError("diagnostic_response_identity_mismatch")
    if (value.get("status") != "blocked" or value.get("terminal") is not True
            or value.get("client_delivery_allowed") is not False
            or value.get("current_stage") != STAGE):
        raise ValueError("diagnostic_not_blocked_final_report")
    failure = _mapping(_mapping(_mapping(value.get("record")).get("stage_results")).get(STAGE))
    if not failure:
        raise ValueError("diagnostic_failure_details_unavailable")
    message = failure.get("error_message")
    message = message if isinstance(message, str) else ""
    matches = [{"file": file, "line": line, "text": text}
               for file, line, text in fragments if text in message][:16]
    safe_failure: dict[str, Any] = {
        key: failure.get(key) if isinstance(failure.get(key), str) and failure[key] in codes
        else "unrecognized" for key in ("reason", "error_code")
    }
    safe_failure.update({"message_sha256": hashlib.sha256(message.encode()).hexdigest(),
                         "source_literal_matches": matches,
                         "matches_are_diagnostic_hints_not_root_cause_proof": True})
    return {"schema": "nico.blocked-run-diagnostic.v1", "run_id": run_id,
            "commit_sha": expected_commit, "stage": STAGE, "status": "blocked",
            "terminal": True, "http_status": 200, "production_modified": False,
            "shipping_clearance": False, "browser_proof_passed": False,
            "payload_sha256": hashlib.sha256(raw).hexdigest(), "failure": safe_failure}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
            or not _RUN.fullmatch(args.run_id) or not _SHA.fullmatch(args.expected_commit)):
        raise ValueError("diagnostic_trusted_main_execution_required")
    from github_actions_nico_proof_auth_v1 import acquire_production_proof_session
    codes, fragments = source_catalog(Path(__file__).resolve().parents[1] / "nico")
    session, _retained = acquire_production_proof_session(ORIGIN)
    with httpx.Client(headers={"X-NICO-Operator-Session": session,
                              "X-NICO-Browser-Projection": "terminal-manifest-v1",
                              "Accept": "application/json", "Cache-Control": "no-store"},
                      timeout=httpx.Timeout(10, connect=5), follow_redirects=False, trust_env=False) as client:
        result = diagnose(client=client, run_id=args.run_id, expected_commit=args.expected_commit,
                          codes=codes, fragments=fragments)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print untrusted responses or authentication exception text.
        print("BLOCKED_RUN_DIAGNOSTIC_FAILED:" + type(exc).__name__, flush=True)
        raise SystemExit(1) from None
