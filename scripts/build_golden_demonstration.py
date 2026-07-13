from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class GoldenDemonstrationFailure(RuntimeError):
    """Raised when the recorded synthetic demonstration cannot be proved safely."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoldenDemonstrationFailure(f"Could not read valid JSON from {path.name}.") from exc
    if not isinstance(value, dict):
        raise GoldenDemonstrationFailure(f"{path.name} must contain a JSON object.")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise GoldenDemonstrationFailure(f"Could not hash {path.name}.") from exc


def _safe_fixture_path(root: Path, relative: Any) -> Path:
    text = str(relative or "").strip()
    if not text or Path(text).name != text or not text.endswith(".json"):
        raise GoldenDemonstrationFailure("Fixture paths must be local JSON filenames without directories.")
    path = (root / text).resolve()
    if path.parent != root.resolve():
        raise GoldenDemonstrationFailure("Fixture path escaped the golden fixture directory.")
    if not path.is_file():
        raise GoldenDemonstrationFailure(f"Declared fixture is missing: {text}.")
    return path


def _is_false(value: Any) -> bool:
    return value is False


def _validate_fixture(entry: dict[str, Any], fixture: dict[str, Any]) -> None:
    fixture_name = str(fixture.get("fixture_name") or "")
    if fixture_name != str(entry.get("fixture_name") or ""):
        raise GoldenDemonstrationFailure(f"Fixture-name mismatch for {entry.get('id') or 'unknown fixture'}.")
    if fixture.get("evidence_kind") != "synthetic" or not _is_false(fixture.get("live_claim")):
        raise GoldenDemonstrationFailure(f"{fixture_name} is not explicitly synthetic and non-live.")

    identity = fixture.get("identity") if isinstance(fixture.get("identity"), dict) else {}
    required_identity = ("run_id", "scan_id", "report_id", "repository", "commit_sha")
    if any(not str(identity.get(key) or "").strip() for key in required_identity):
        raise GoldenDemonstrationFailure(f"{fixture_name} is missing an exact fixture identity.")
    if not str(identity.get("run_id")).startswith("synthetic-"):
        raise GoldenDemonstrationFailure(f"{fixture_name} run identity is not synthetic.")
    if not str(identity.get("scan_id")).startswith("synthetic-"):
        raise GoldenDemonstrationFailure(f"{fixture_name} scan identity is not synthetic.")
    if not str(identity.get("report_id")).startswith("synthetic-"):
        raise GoldenDemonstrationFailure(f"{fixture_name} report identity is not synthetic.")
    if not str(identity.get("repository")).startswith("example.invalid/"):
        raise GoldenDemonstrationFailure(f"{fixture_name} repository identity is not non-production.")

    review = fixture.get("review") if isinstance(fixture.get("review"), dict) else {}
    if review.get("status") != "required" or review.get("approved") is not False or review.get("client_ready") is not False:
        raise GoldenDemonstrationFailure(f"{fixture_name} weakened the human-review or client-readiness boundary.")

    delivery = fixture.get("delivery") if isinstance(fixture.get("delivery"), dict) else {}
    if delivery.get("status") != "blocked":
        raise GoldenDemonstrationFailure(f"{fixture_name} did not keep synthetic delivery blocked.")

    score = fixture.get("score") if isinstance(fixture.get("score"), dict) else {}
    if score.get("certification") is True:
        raise GoldenDemonstrationFailure(f"{fixture_name} incorrectly claims certification.")
    if isinstance(score.get("value"), (int, float)):
        if score.get("source") != "fixture_only" or "synthetic" not in str(score.get("status") or ""):
            raise GoldenDemonstrationFailure(f"{fixture_name} numeric score is not clearly fixture-only and synthetic.")

    repair = fixture.get("repair") or fixture.get("repair_plan") or {}
    if isinstance(repair, dict) and repair.get("automatic_production_change_allowed") is True:
        raise GoldenDemonstrationFailure(f"{fixture_name} allows an automatic production change.")


def _fixture_summary(entry: dict[str, Any], fixture: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    evidence = [item for item in fixture.get("evidence") or [] if isinstance(item, dict)]
    evidence_counts = Counter(str(item.get("status") or "unknown") for item in evidence)
    findings = [item for item in fixture.get("findings") or [] if isinstance(item, dict)]
    repair = fixture.get("repair_plan") if isinstance(fixture.get("repair_plan"), dict) else fixture.get("repair")
    repair = repair if isinstance(repair, dict) else {}
    candidates = [item for item in repair.get("candidates") or [] if isinstance(item, dict)]
    score = fixture.get("score") if isinstance(fixture.get("score"), dict) else {}
    identity = fixture["identity"]

    return {
        "id": str(entry.get("id") or ""),
        "fixture_name": fixture["fixture_name"],
        "source_file": str(entry.get("path") or ""),
        "source_sha256": source_sha256,
        "coverage": sorted({str(item) for item in entry.get("coverage") or [] if str(item)}),
        "identity": {
            "run_id": identity["run_id"],
            "scan_id": identity["scan_id"],
            "report_id": identity["report_id"],
            "repository": identity["repository"],
            "commit_sha": identity["commit_sha"],
        },
        "evidence_status_counts": dict(sorted(evidence_counts.items())),
        "finding_count": len(findings),
        "repair_candidate_count": len(candidates),
        "score": {
            "value": score.get("value"),
            "status": score.get("status") or "not_supplied",
            "source": score.get("source") or "not_supplied",
            "certification": bool(score.get("certification")),
        },
        "review": {
            "status": fixture["review"]["status"],
            "approved": fixture["review"]["approved"],
            "client_ready": fixture["review"]["client_ready"],
        },
        "delivery_status": fixture["delivery"]["status"],
        "live_claim": fixture["live_claim"],
    }


def build_golden_demonstration(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = _load_json(manifest_path)
    if manifest.get("evidence_kind") != "synthetic_fixture_manifest" or manifest.get("live_claim") is not False:
        raise GoldenDemonstrationFailure("Golden manifest must be explicitly synthetic and non-live.")

    raw_entries = manifest.get("fixtures")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise GoldenDemonstrationFailure("Golden manifest must declare at least one fixture.")

    entries: list[dict[str, Any]] = []
    fixture_ids: set[str] = set()
    fixture_names: set[str] = set()
    run_ids: set[str] = set()
    coverage: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise GoldenDemonstrationFailure("Every golden manifest fixture entry must be an object.")
        fixture_id = str(raw_entry.get("id") or "").strip()
        if not fixture_id or fixture_id in fixture_ids:
            raise GoldenDemonstrationFailure("Golden fixture IDs must be non-empty and unique.")
        fixture_ids.add(fixture_id)
        fixture_path = _safe_fixture_path(manifest_path.parent, raw_entry.get("path"))
        fixture = _load_json(fixture_path)
        _validate_fixture(raw_entry, fixture)
        fixture_name = str(fixture.get("fixture_name") or "")
        run_id = str((fixture.get("identity") or {}).get("run_id") or "")
        if fixture_name in fixture_names or run_id in run_ids:
            raise GoldenDemonstrationFailure("Golden fixture names and run identities must be unique.")
        fixture_names.add(fixture_name)
        run_ids.add(run_id)
        coverage.update(str(item) for item in raw_entry.get("coverage") or [] if str(item))
        entries.append(_fixture_summary(raw_entry, fixture, _sha256(fixture_path)))

    required_coverage = {str(item) for item in manifest.get("coverage_requirements") or [] if str(item)}
    if coverage != required_coverage:
        missing = sorted(required_coverage - coverage)
        unexpected = sorted(coverage - required_coverage)
        raise GoldenDemonstrationFailure(
            f"Golden coverage mismatch; missing={','.join(missing) or 'none'}; unexpected={','.join(unexpected) or 'none'}."
        )

    entries.sort(key=lambda item: item["id"])
    return {
        "artifact_schema": "nico.golden_demonstration.v1",
        "status": "passed",
        "demonstration_kind": "recorded_synthetic_golden_suite",
        "synthetic": True,
        "live_claim": False,
        "manifest": {
            "path": manifest_path.name,
            "sha256": _sha256(manifest_path),
            "version": manifest.get("manifest_version"),
            "suite_name": manifest.get("suite_name"),
        },
        "fixture_count": len(entries),
        "fixtures": entries,
        "coverage": sorted(coverage),
        "boundaries": {
            "all_synthetic": all(item["live_claim"] is False for item in entries),
            "all_review_required": all(item["review"]["status"] == "required" for item in entries),
            "none_approved": all(item["review"]["approved"] is False for item in entries),
            "none_client_ready": all(item["review"]["client_ready"] is False for item in entries),
            "all_delivery_blocked": all(item["delivery_status"] == "blocked" for item in entries),
            "no_certification_claim": all(item["score"]["certification"] is False for item in entries),
        },
        "guardrail": "This is a deterministic recorded demonstration of synthetic fixture contracts. It is not a live assessment, production smoke result, certification, approval, repair execution, or client-delivery artifact.",
    }


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# NICO Recorded Synthetic Golden Demonstration",
        "",
        f"- Status: **{artifact['status']}**",
        f"- Fixture count: **{artifact['fixture_count']}**",
        f"- Manifest SHA-256: `{artifact['manifest']['sha256']}`",
        "- Live claim: **false**",
        "",
        "## Fixtures",
        "",
        "| Fixture | Evidence states | Findings | Repair candidates | Score status | Review | Delivery |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for item in artifact["fixtures"]:
        evidence_states = ", ".join(
            f"{status}={count}" for status, count in item["evidence_status_counts"].items()
        ) or "none"
        lines.append(
            "| "
            + " | ".join(
                [
                    item["fixture_name"],
                    evidence_states,
                    str(item["finding_count"]),
                    str(item["repair_candidate_count"]),
                    str(item["score"]["status"]),
                    str(item["review"]["status"]),
                    str(item["delivery_status"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            *[f"- `{item}`" for item in artifact["coverage"]],
            "",
            "## Guardrail",
            "",
            artifact["guardrail"],
            "",
        ]
    )
    return "\n".join(lines)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic recorded demonstration from NICO synthetic golden fixtures.")
    parser.add_argument(
        "--manifest",
        default="tests/fixtures/golden/manifest.json",
        help="Path to the canonical synthetic golden fixture manifest.",
    )
    parser.add_argument("--output-json", default="audit-results/golden-demonstration.json")
    parser.add_argument("--output-markdown", default="audit-results/golden-demonstration.md")
    args = parser.parse_args()
    try:
        artifact = build_golden_demonstration(Path(args.manifest))
        _write(Path(args.output_json), json.dumps(artifact, indent=2, sort_keys=True) + "\n")
        _write(Path(args.output_markdown), render_markdown(artifact))
        print(json.dumps({"status": "passed", "fixture_count": artifact["fixture_count"]}, sort_keys=True))
        return 0
    except GoldenDemonstrationFailure as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
