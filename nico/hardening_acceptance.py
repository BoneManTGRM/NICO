from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from nico.post_release_hardening import HardeningScenario, REQUIRED_SCENARIOS


class HardeningAcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class StabilityThresholds:
    max_runtime_regression_ratio: float = 0.25
    max_memory_regression_ratio: float = 0.25
    max_artifact_size_regression_ratio: float = 0.10

    def validate(self) -> None:
        for value in (
            self.max_runtime_regression_ratio,
            self.max_memory_regression_ratio,
            self.max_artifact_size_regression_ratio,
        ):
            if value < 0 or value > 5:
                raise ValueError("hardening_stability_threshold_invalid")


@dataclass(frozen=True)
class HardeningPass:
    path: str
    expected_sha: str
    observations: Mapping[str, Mapping[str, Any]]
    verdict: Mapping[str, Any]
    truth_fingerprint: str


@dataclass(frozen=True)
class HardeningAcceptance:
    expected_sha: str
    pass_one_fingerprint: str
    pass_two_fingerprint: str
    accepted: bool
    issues: tuple[str, ...]
    scenario_results: Mapping[str, Mapping[str, Any]]


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HardeningAcceptanceError(code)
    return value


def _load(path: str | Path) -> HardeningPass:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HardeningAcceptanceError("hardening_evidence_unreadable") from exc
    if payload.get("artifact_schema") != "nico.post_release_hardening.v1":
        raise HardeningAcceptanceError("hardening_evidence_schema_invalid")
    expected_sha = str(payload.get("expected_sha") or "")
    if len(expected_sha) != 40:
        raise HardeningAcceptanceError("hardening_evidence_exact_sha_invalid")
    verdict = _mapping(payload.get("verdict"), "hardening_verdict_missing")
    observations_raw = payload.get("observations")
    if not isinstance(observations_raw, list):
        raise HardeningAcceptanceError("hardening_observations_missing")
    observations: dict[str, Mapping[str, Any]] = {}
    for raw in observations_raw:
        item = _mapping(raw, "hardening_observation_invalid")
        scenario = str(item.get("scenario") or "")
        try:
            HardeningScenario(scenario)
        except ValueError as exc:
            raise HardeningAcceptanceError("hardening_scenario_invalid") from exc
        if scenario in observations:
            raise HardeningAcceptanceError("hardening_scenario_duplicate")
        observations[scenario] = item
    required = {scenario.value for scenario in REQUIRED_SCENARIOS}
    if set(observations) != required:
        raise HardeningAcceptanceError("hardening_scenario_set_incomplete")
    if verdict.get("status") != "passed":
        raise HardeningAcceptanceError("hardening_pass_verdict_not_passed")
    if verdict.get("expected_sha") != expected_sha:
        raise HardeningAcceptanceError("hardening_verdict_sha_mismatch")
    if payload.get("human_review_required") is not True:
        raise HardeningAcceptanceError("hardening_human_review_boundary_missing")
    if payload.get("client_delivery_allowed") is not False:
        raise HardeningAcceptanceError("hardening_delivery_boundary_invalid")
    truth = {
        scenario: {
            "exact_sha": item.get("exact_sha"),
            "status": item.get("status"),
            "terminal": item.get("terminal"),
            "human_review_required": item.get("human_review_required"),
            "client_delivery_allowed": item.get("client_delivery_allowed"),
            "evidence": item.get("evidence") or {},
        }
        for scenario, item in sorted(observations.items())
    }
    rendered = json.dumps(truth, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = f"sha256:{sha256(rendered.encode('utf-8')).hexdigest()}"
    return HardeningPass(
        path=str(source),
        expected_sha=expected_sha,
        observations=observations,
        verdict=verdict,
        truth_fingerprint=fingerprint,
    )


def _ratio(first: float, second: float) -> float:
    if first <= 0:
        return 0.0 if second <= 0 else float("inf")
    return max(0.0, (second - first) / first)


def evaluate_two_pass_acceptance(
    pass_one_path: str | Path,
    pass_two_path: str | Path,
    *,
    expected_sha: str = "",
    thresholds: StabilityThresholds | None = None,
) -> HardeningAcceptance:
    selected = thresholds or StabilityThresholds()
    selected.validate()
    first = _load(pass_one_path)
    second = _load(pass_two_path)
    issues: list[str] = []
    if first.expected_sha != second.expected_sha:
        issues.append("hardening_two_pass_sha_mismatch")
    pinned_sha = expected_sha or first.expected_sha
    if pinned_sha != first.expected_sha or pinned_sha != second.expected_sha:
        issues.append("hardening_expected_sha_mismatch")
    if first.truth_fingerprint != second.truth_fingerprint:
        issues.append("hardening_truth_fingerprint_mismatch")

    results: dict[str, dict[str, Any]] = {}
    for scenario in sorted(first.observations):
        one = first.observations[scenario]
        two = second.observations[scenario]
        scenario_issues: list[str] = []
        if one.get("exact_sha") != pinned_sha or two.get("exact_sha") != pinned_sha:
            scenario_issues.append("scenario_exact_sha_mismatch")
        if one.get("human_review_required") is not True or two.get("human_review_required") is not True:
            scenario_issues.append("scenario_human_review_boundary_missing")
        if one.get("client_delivery_allowed") is not False or two.get("client_delivery_allowed") is not False:
            scenario_issues.append("scenario_delivery_boundary_invalid")
        runtime_ratio = _ratio(float(one.get("runtime_seconds") or 0), float(two.get("runtime_seconds") or 0))
        memory_ratio = _ratio(float(one.get("peak_memory_mb") or 0), float(two.get("peak_memory_mb") or 0))
        artifact_ratio = _ratio(float(one.get("artifact_bytes") or 0), float(two.get("artifact_bytes") or 0))
        if runtime_ratio > selected.max_runtime_regression_ratio:
            scenario_issues.append("scenario_runtime_regression_exceeded")
        if memory_ratio > selected.max_memory_regression_ratio:
            scenario_issues.append("scenario_memory_regression_exceeded")
        if artifact_ratio > selected.max_artifact_size_regression_ratio:
            scenario_issues.append("scenario_artifact_size_regression_exceeded")
        if scenario_issues:
            issues.extend(f"{scenario}:{item}" for item in scenario_issues)
        results[scenario] = {
            "passed": not scenario_issues,
            "issues": scenario_issues,
            "runtime_regression_ratio": runtime_ratio,
            "memory_regression_ratio": memory_ratio,
            "artifact_size_regression_ratio": artifact_ratio,
            "pass_one_runtime_seconds": float(one.get("runtime_seconds") or 0),
            "pass_two_runtime_seconds": float(two.get("runtime_seconds") or 0),
            "pass_one_peak_memory_mb": float(one.get("peak_memory_mb") or 0),
            "pass_two_peak_memory_mb": float(two.get("peak_memory_mb") or 0),
            "pass_one_artifact_bytes": int(one.get("artifact_bytes") or 0),
            "pass_two_artifact_bytes": int(two.get("artifact_bytes") or 0),
        }

    return HardeningAcceptance(
        expected_sha=pinned_sha,
        pass_one_fingerprint=first.truth_fingerprint,
        pass_two_fingerprint=second.truth_fingerprint,
        accepted=not issues,
        issues=tuple(issues),
        scenario_results=results,
    )


def acceptance_mapping(result: HardeningAcceptance) -> dict[str, Any]:
    return {
        "artifact_schema": "nico.post_release_hardening_acceptance.v1",
        "status": "passed" if result.accepted else "failed",
        "expected_sha": result.expected_sha,
        "passes_required": 2,
        "passes_completed": 2,
        "pass_one_truth_fingerprint": result.pass_one_fingerprint,
        "pass_two_truth_fingerprint": result.pass_two_fingerprint,
        "truth_fingerprints_match": result.pass_one_fingerprint == result.pass_two_fingerprint,
        "issues": list(result.issues),
        "scenarios": dict(result.scenario_results),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "HardeningAcceptance",
    "HardeningAcceptanceError",
    "HardeningPass",
    "StabilityThresholds",
    "acceptance_mapping",
    "evaluate_two_pass_acceptance",
]
