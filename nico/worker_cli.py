from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nico.worker_execution import (
    WorkerLimits,
    checkout_repository,
    make_workspace,
    validate_ref,
    validate_repository,
    workspace_from_temp,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local NICO worker checkout skeleton.")
    parser.add_argument("repository", help="GitHub repository in owner/name form")
    parser.add_argument("ref", help="Branch, tag, or safe ref to check out")
    parser.add_argument("--timeout", type=int, default=120, help="Checkout timeout in seconds")
    parser.add_argument("--max-output", type=int, default=12000, help="Maximum captured output characters")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repository = validate_repository(args.repository)
        ref = validate_ref(args.ref)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    with make_workspace() as temp_dir:
        workspace = workspace_from_temp(temp_dir)
        result = checkout_repository(
            repository,
            ref,
            workspace,
            limits=WorkerLimits(timeout_seconds=args.timeout, max_output_chars=args.max_output),
        )
        payload = {
            "ok": result.ok,
            "repository": repository,
            "ref": ref,
            "repo_dir": str(Path(workspace.repo_dir)),
            "checkout": {
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "output_truncated": result.output_truncated,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
