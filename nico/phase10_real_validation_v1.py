from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

VERSION = "nico.phase10_real_validation.v1"

_ALLOWED_AUTOMATED_DISPOSITIONS = {
    "confirmed",
    "disputed",
    "false_positive",
    "duplicate_prevented",
    "not_independently_reviewed",
}
_ALLOWED_HUMAN_DISPOSITIONS = {"possible_false_negative", "not_applicable"}
_TERMINAL_TOKEN_RE = re.compile(
    r"(?:final|draft|pending[-_ ]approval|approved|rejected|borrador|pendiente[-_ ]de[-_ ]aprobaci[oó]n)",
    re.IGNORECASE,
)
_GENERIC_TITLES = {
    "finding",
    "issue",
    "priority finding",
    "high priority finding",
    "medium priority finding",
    "low priority finding",
    "security issue",
    "code quality issue",
}


class Phase10ValidationError(ValueError):
    """Raised when retained validation evidence is incomplete or contradictory."""


@dataclass(frozen=True)
class AggregateMetrics:
    independently_reviewed: int
    confirmed: int
    false_positives: int
    disputed: int
    possible_false_negatives: int
    precision: float | None
    recall_proxy: float | None
    severity_agreement: float | None
    remediation_usefulness: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "independently_reviewed": self.independently_reviewed,
            "confirmed": self.confirmed,
            "false_positives": self.false_positives,
            "disputed": self.disputed,
            "possible_false_negatives": self.possible_false_negatives,
            "precision": self.precision,
            "recall_proxy": self.recall_proxy,
            "severity_agreement": self.severity_agreement,
            "remediation_usefulness": self.remediation_usefulness,
        }


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Phase10ValidationError(f"{label} must be an object")
    return value


def _require_nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Phase10ValidationError(f"{label} must be non-empty text")
    return value.strip()


def _require_sha(value: Any, label: str) -> str:
    text = _require_nonempty_text(value, label).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", text):
        raise Phase10ValidationError(f"{label} must be a full 40-character commit SHA")
    return text


def _canonical_json_sha(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _terminal_tokens(filename: str) -> list[str]:
    return [match.group(0).lower().replace("_", "-").replace(" ", "-") for match in _TERMINAL_TOKEN_RE.finditer(filename)]


def _validate_filename(filename: Any, label: str) -> str:
    text = _require_nonempty_text(filename, label)
    tokens = _terminal_tokens(text)
    if len(tokens) > 1:
        raise Phase10ValidationError(f"{label} contains repeated or contradictory terminal-state tokens: {tokens}")
    return text


def _validate_bandit(record: Mapping[str, Any], expected_sha: str) -> None:
    status = _require_nonempty_text(record.get("status"), "bandit.status")
    if status == "not_applicable":
        return
    if status != "completed":
        raise Phase10ValidationError("Bandit must be completed or explicitly not_applicable")
    if _require_sha(record.get("commit_sha"), "bandit.commit_sha") != expected_sha:
        raise Phase10ValidationError("Bandit evidence is bound to the wrong revision")
    exit_code = record.get("exit_code")
    if exit_code not in (0, 1):
        raise Phase10ValidationError("Bandit completed status requires exit code 0 or 1")
    if not isinstance(record.get("finding_count"), int) or record["finding_count"] < 0:
        raise Phase10ValidationError("bandit.finding_count must be a non-negative integer")
    _require_nonempty_text(record.get("command"), "bandit.command")
    _require_nonempty_text(record.get("version"), "bandit.version")
    output_hash = _require_nonempty_text(record.get("output_sha256"), "bandit.output_sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", output_hash.lower()):
        raise Phase10ValidationError("bandit.output_sha256 must be a SHA-256 digest")
    if record.get("json_parseable") is not True:
        raise Phase10ValidationError("Bandit JSON output must be parseable")


def _finding_key(finding: Mapping[str, Any]) -> tuple[str, str, str]:
    location = str(finding.get("location") or "").strip().lower()
    category = str(finding.get("category") or "").strip().lower()
    meaning = str(finding.get("decision_meaning") or finding.get("title") or "").strip().lower()
    return location, category, meaning


def _validate_findings(findings: Sequence[Any]) -> None:
    seen_ids: set[str] = set()
    seen_semantic: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(findings):
        finding = _require_mapping(raw, f"findings[{index}]")
        finding_id = _require_nonempty_text(finding.get("finding_id") or finding.get("id"), f"findings[{index}].finding_id")
        if finding_id in seen_ids:
            raise Phase10ValidationError(f"duplicate finding id: {finding_id}")
        seen_ids.add(finding_id)
        title = _require_nonempty_text(finding.get("title"), f"findings[{index}].title")
        if title.strip().lower() in _GENERIC_TITLES:
            raise Phase10ValidationError(f"generic finding title is not allowed: {title}")
        semantic = _finding_key(finding)
        if all(semantic) and semantic in seen_semantic:
            raise Phase10ValidationError(f"semantic duplicate finding detected: {finding_id}")
        if all(semantic):
            seen_semantic.add(semantic)
        criteria = finding.get("acceptance_criteria") or []
        if not isinstance(criteria, Sequence) or isinstance(criteria, (str, bytes)):
            raise Phase10ValidationError(f"findings[{index}].acceptance_criteria must be a list")
        normalized = [re.sub(r"\s+", " ", str(item)).strip().lower() for item in criteria]
        if len(normalized) != len(set(normalized)):
            raise Phase10ValidationError(f"duplicate acceptance criteria in finding {finding_id}")


def _validate_surface_consistency(target: Mapping[str, Any]) -> None:
    counts = target.get("surface_finding_counts")
    if not isinstance(counts, Mapping) or not counts:
        raise Phase10ValidationError("surface_finding_counts must retain every report/export surface")
    required = {"executive", "detailed", "roadmap", "backlog", "remediation", "json", "csv", "english_pdf", "spanish_pdf"}
    missing = required.difference(counts)
    if missing:
        raise Phase10ValidationError(f"missing finding-count surfaces: {sorted(missing)}")
    values = {counts[name] for name in required}
    if len(values) != 1 or not all(isinstance(value, int) and value >= 0 for value in values):
        raise Phase10ValidationError("all canonical report surfaces must contain the same non-negative finding count")


def validate_target(target: Mapping[str, Any]) -> dict[str, Any]:
    repository = _require_nonempty_text(target.get("repository"), "repository")
    commit_sha = _require_sha(target.get("commit_sha"), "commit_sha")
    _require_nonempty_text(target.get("run_id"), "run_id")
    _require_nonempty_text(target.get("started_at"), "started_at")
    _require_nonempty_text(target.get("completed_at"), "completed_at")

    artifacts = _require_mapping(target.get("artifacts"), "artifacts")
    required_artifacts = {
        "canonical_json",
        "findings_csv",
        "english_pdf",
        "spanish_pdf",
        "release_gate",
        "package_manifest",
    }
    for name in required_artifacts:
        artifact = _require_mapping(artifacts.get(name), f"artifacts.{name}")
        _require_nonempty_text(artifact.get("path"), f"artifacts.{name}.path")
        digest = _require_nonempty_text(artifact.get("sha256"), f"artifacts.{name}.sha256").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise Phase10ValidationError(f"artifacts.{name}.sha256 must be a SHA-256 digest")
        if not isinstance(artifact.get("bytes"), int) or artifact["bytes"] <= 0:
            raise Phase10ValidationError(f"artifacts.{name}.bytes must be positive")

    filenames = _require_mapping(target.get("filenames"), "filenames")
    _validate_filename(filenames.get("english_pdf"), "filenames.english_pdf")
    _validate_filename(filenames.get("spanish_pdf"), "filenames.spanish_pdf")

    findings = target.get("findings")
    if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)):
        raise Phase10ValidationError("findings must be a list")
    _validate_findings(findings)
    _validate_surface_consistency(target)

    scanner_records = target.get("scanner_records")
    if not isinstance(scanner_records, Sequence) or isinstance(scanner_records, (str, bytes)):
        raise Phase10ValidationError("scanner_records must be a list")
    bandit = next((item for item in scanner_records if isinstance(item, Mapping) and item.get("scanner") == "bandit"), None)
    if bandit is None:
        raise Phase10ValidationError("a Bandit execution record is required for every target")
    _validate_bandit(bandit, commit_sha)

    if target.get("production_path_integrated") is not True:
        raise Phase10ValidationError("production_path_integrated must be true")
    if target.get("release_gate_passed") is not True:
        raise Phase10ValidationError("release_gate_passed must be true")
    if target.get("client_delivery_state") not in {"blocked_pending_human_approval", "approved_exact_package"}:
        raise Phase10ValidationError("client delivery must remain blocked or be tied to exact-package approval")

    return {
        "repository": repository,
        "commit_sha": commit_sha,
        "run_id": target["run_id"],
        "finding_count": len(findings),
        "target_evidence_sha256": _canonical_json_sha(target),
        "valid": True,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def aggregate_human_comparison(entries: Iterable[Mapping[str, Any]]) -> AggregateMetrics:
    independently_reviewed = confirmed = false_positives = disputed = possible_false_negatives = 0
    severity_total = severity_agreed = usefulness_total = usefulness_positive = 0

    for index, entry in enumerate(entries):
        kind = _require_nonempty_text(entry.get("kind"), f"comparison[{index}].kind")
        disposition = _require_nonempty_text(entry.get("disposition"), f"comparison[{index}].disposition")
        reviewer = entry.get("reviewer")
        if disposition not in {"not_independently_reviewed", "not_applicable"}:
            reviewer_obj = _require_mapping(reviewer, f"comparison[{index}].reviewer")
            _require_nonempty_text(reviewer_obj.get("name"), f"comparison[{index}].reviewer.name")
            _require_nonempty_text(reviewer_obj.get("role"), f"comparison[{index}].reviewer.role")
            if reviewer_obj.get("independent") is not True:
                raise Phase10ValidationError("human comparison reviewer must be independent")

        if kind == "automated_finding":
            if disposition not in _ALLOWED_AUTOMATED_DISPOSITIONS:
                raise Phase10ValidationError(f"invalid automated finding disposition: {disposition}")
            if disposition != "not_independently_reviewed":
                independently_reviewed += 1
            if disposition == "confirmed":
                confirmed += 1
            elif disposition == "false_positive":
                false_positives += 1
            elif disposition == "disputed":
                disputed += 1
        elif kind == "human_only_finding":
            if disposition not in _ALLOWED_HUMAN_DISPOSITIONS:
                raise Phase10ValidationError(f"invalid human-only disposition: {disposition}")
            if disposition == "possible_false_negative":
                possible_false_negatives += 1
        else:
            raise Phase10ValidationError(f"unknown comparison kind: {kind}")

        severity = entry.get("severity_agreement")
        if severity is not None:
            if not isinstance(severity, bool):
                raise Phase10ValidationError("severity_agreement must be boolean or null")
            severity_total += 1
            severity_agreed += int(severity)
        usefulness = entry.get("remediation_useful")
        if usefulness is not None:
            if not isinstance(usefulness, bool):
                raise Phase10ValidationError("remediation_useful must be boolean or null")
            usefulness_total += 1
            usefulness_positive += int(usefulness)

    return AggregateMetrics(
        independently_reviewed=independently_reviewed,
        confirmed=confirmed,
        false_positives=false_positives,
        disputed=disputed,
        possible_false_negatives=possible_false_negatives,
        precision=_ratio(confirmed, confirmed + false_positives),
        recall_proxy=_ratio(confirmed, confirmed + possible_false_negatives),
        severity_agreement=_ratio(severity_agreed, severity_total),
        remediation_usefulness=_ratio(usefulness_positive, usefulness_total),
    )


def validate_phase10_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    schema = _require_nonempty_text(bundle.get("schema"), "schema")
    if schema != VERSION:
        raise Phase10ValidationError(f"unsupported schema: {schema}")
    targets = bundle.get("targets")
    if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)) or len(targets) < 3:
        raise Phase10ValidationError("Phase 10 requires at least three validation targets")
    validated_targets = [validate_target(_require_mapping(target, f"targets[{index}]")) for index, target in enumerate(targets)]
    repositories = {item["repository"] for item in validated_targets}
    if "BoneManTGRM/NICO" not in repositories:
        raise Phase10ValidationError("Phase 10 requires a NICO self-assessment")
    if len(repositories - {"BoneManTGRM/NICO"}) < 2:
        raise Phase10ValidationError("Phase 10 requires at least two unrelated repositories")

    comparison = bundle.get("human_comparison")
    if not isinstance(comparison, Sequence) or isinstance(comparison, (str, bytes)):
        raise Phase10ValidationError("human_comparison must be a list")
    metrics = aggregate_human_comparison(_require_mapping(item, f"human_comparison[{index}]") for index, item in enumerate(comparison))
    if metrics.independently_reviewed == 0:
        raise Phase10ValidationError("Phase 10 cannot complete without independent human review")

    conclusion = _require_mapping(bundle.get("conclusion"), "conclusion")
    recommendation = _require_nonempty_text(conclusion.get("recommendation"), "conclusion.recommendation")
    if recommendation not in {"release", "release_with_limitations", "reject"}:
        raise Phase10ValidationError("invalid release recommendation")
    limitations = conclusion.get("limitations")
    if not isinstance(limitations, Sequence) or isinstance(limitations, (str, bytes)) or not limitations:
        raise Phase10ValidationError("an explicit non-empty limitations list is required")

    result = {
        "schema": VERSION,
        "valid": True,
        "target_count": len(validated_targets),
        "targets": validated_targets,
        "metrics": metrics.as_dict(),
        "recommendation": recommendation,
        "limitations": list(limitations),
        "claim_boundary": "Measured statements are limited to retained tested repositories; no consulting-replacement claim is authorized.",
    }
    result["validation_bundle_sha256"] = _canonical_json_sha(result)
    return result


__all__ = [
    "VERSION",
    "AggregateMetrics",
    "Phase10ValidationError",
    "aggregate_human_comparison",
    "validate_phase10_bundle",
    "validate_target",
]
