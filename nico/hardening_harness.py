from __future__ import annotations

import json
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from nico.post_release_hardening import (
    HardeningObservation,
    HardeningScenario,
    PerformanceBudget,
    evaluate_matrix,
)


class HardeningHarnessError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardeningCase:
    scenario: HardeningScenario
    runner: Callable[[], Mapping[str, Any]]
    artifact_keys: tuple[str, ...] = ("markdown", "html", "pdf", "json")


@dataclass(frozen=True)
class HardeningRun:
    expected_sha: str
    observations: tuple[HardeningObservation, ...]
    verdict: Mapping[str, Any]


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, sort_keys=True, default=str).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise HardeningHarnessError("hardening_result_not_serializable") from exc


def _artifact_size(payload: Mapping[str, Any], keys: Iterable[str]) -> int:
    total = 0
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, bytes):
            total += len(value)
        elif isinstance(value, str):
            total += len(value.encode("utf-8"))
        else:
            total += _json_size(value)
    return total


def run_case(case: HardeningCase, *, expected_sha: str) -> HardeningObservation:
    tracemalloc.start()
    started = time.perf_counter()
    try:
        payload = case.runner()
    except Exception as exc:
        payload = {
            "status": "failed",
            "terminal": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "error_type": type(exc).__name__,
            "error_code": str(exc),
        }
    runtime = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if not isinstance(payload, Mapping):
        raise HardeningHarnessError("hardening_runner_must_return_mapping")
    exact_sha = str(payload.get("exact_sha") or expected_sha)
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}
    return HardeningObservation(
        scenario=case.scenario,
        exact_sha=exact_sha,
        status=str(payload.get("status") or "failed"),
        terminal=bool(payload.get("terminal")),
        human_review_required=bool(payload.get("human_review_required", True)),
        client_delivery_allowed=bool(payload.get("client_delivery_allowed", False)),
        runtime_seconds=runtime,
        peak_memory_mb=peak / (1024 * 1024),
        artifact_bytes=_artifact_size(payload, case.artifact_keys),
        evidence=dict(evidence),
    )


def run_hardening_matrix(
    cases: Iterable[HardeningCase],
    *,
    expected_sha: str,
    budgets: Mapping[HardeningScenario, PerformanceBudget] | None = None,
) -> HardeningRun:
    observations = tuple(run_case(case, expected_sha=expected_sha) for case in cases)
    verdict = evaluate_matrix(observations, expected_sha=expected_sha, budgets=budgets)
    return HardeningRun(expected_sha, observations, verdict)


def observation_to_mapping(observation: HardeningObservation) -> dict[str, Any]:
    return {
        "scenario": observation.scenario.value,
        "exact_sha": observation.exact_sha,
        "status": observation.status,
        "terminal": observation.terminal,
        "human_review_required": observation.human_review_required,
        "client_delivery_allowed": observation.client_delivery_allowed,
        "runtime_seconds": observation.runtime_seconds,
        "peak_memory_mb": observation.peak_memory_mb,
        "artifact_bytes": observation.artifact_bytes,
        "evidence": dict(observation.evidence or {}),
    }


def write_hardening_evidence(run: HardeningRun, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_schema": "nico.post_release_hardening.v1",
        "expected_sha": run.expected_sha,
        "observations": [observation_to_mapping(item) for item in run.observations],
        "verdict": dict(run.verdict),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output


def load_observations(path: str | Path) -> tuple[str, tuple[HardeningObservation, ...]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_sha = str(payload.get("expected_sha") or "")
    if not expected_sha:
        raise HardeningHarnessError("hardening_expected_sha_required")
    observations: list[HardeningObservation] = []
    for raw in payload.get("observations") or ():
        if not isinstance(raw, Mapping):
            raise HardeningHarnessError("hardening_observation_invalid")
        observations.append(
            HardeningObservation(
                scenario=HardeningScenario(str(raw.get("scenario") or "")),
                exact_sha=str(raw.get("exact_sha") or ""),
                status=str(raw.get("status") or ""),
                terminal=bool(raw.get("terminal")),
                human_review_required=bool(raw.get("human_review_required")),
                client_delivery_allowed=bool(raw.get("client_delivery_allowed")),
                runtime_seconds=float(raw.get("runtime_seconds") or 0),
                peak_memory_mb=float(raw.get("peak_memory_mb") or 0),
                artifact_bytes=int(raw.get("artifact_bytes") or 0),
                evidence=dict(raw.get("evidence") or {}),
            )
        )
    return expected_sha, tuple(observations)


_PSEUDO_MAP = str.maketrans(
    {
        "a": "á",
        "e": "ë",
        "i": "ï",
        "o": "ô",
        "u": "ü",
        "A": "Å",
        "E": "Ë",
        "I": "Ï",
        "O": "Ø",
        "U": "Û",
    }
)


def pseudo_localize(text: str, *, expansion_ratio: float = 0.35) -> str:
    source = str(text)
    if expansion_ratio < 0:
        raise ValueError("pseudo_localization_expansion_invalid")
    transformed = source.translate(_PSEUDO_MAP)
    padding = "~" * max(1, int(len(source) * expansion_ratio)) if source else ""
    return f"⟦{transformed}{padding}⟧"


def accessibility_evidence(
    *,
    keyboard: bool,
    screen_reader: bool,
    contrast: bool,
    reduced_motion: bool,
    semantic_headings: bool,
    focus_order: bool,
) -> dict[str, bool]:
    return {
        "keyboard": bool(keyboard),
        "screen_reader": bool(screen_reader),
        "contrast": bool(contrast),
        "reduced_motion": bool(reduced_motion),
        "semantic_headings": bool(semantic_headings),
        "focus_order": bool(focus_order),
    }


__all__ = [
    "HardeningCase",
    "HardeningHarnessError",
    "HardeningRun",
    "accessibility_evidence",
    "load_observations",
    "observation_to_mapping",
    "pseudo_localize",
    "run_case",
    "run_hardening_matrix",
    "write_hardening_evidence",
]
