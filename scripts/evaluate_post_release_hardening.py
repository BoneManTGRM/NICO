from __future__ import annotations

import argparse
import json
from pathlib import Path

from nico.hardening_harness import load_observations
from nico.post_release_hardening import evaluate_matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retained NICO post-release hardening evidence.")
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    expected_sha, observations = load_observations(args.evidence)
    verdict = evaluate_matrix(observations, expected_sha=expected_sha)
    rendered = json.dumps(verdict, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if verdict["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
