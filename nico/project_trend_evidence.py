from __future__ import annotations

from typing import Any

from nico.storage import STORE


def _safe_score(value: Any) -> int | None:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def _payload_score(payload: dict[str, Any]) -> int | None:
    maturity = payload.get("maturity_signal") if isinstance(payload, dict) else None
    if not isinstance(maturity, dict):
        return None
    return _safe_score(maturity.get("score"))


def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def _generated_at(row: dict[str, Any]) -> str:
    payload = _row_payload(row)
    return str(payload.get("generated_at") or row.get("updated_at") or row.get("created_at") or "")


def _project_id(result: dict[str, Any]) -> str:
    return str(result.get("project_id") or result.get("project", {}).get("project_id") or "default_project")


def project_trend_evidence(result: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    resolved_project_id = project_id or _project_id(result)
    current_score = _safe_score((result.get("maturity_signal") or {}).get("score"))
    current_generated_at = str(result.get("generated_at") or "")
    rows = STORE.list("assessment_runs", project_id=resolved_project_id)
    prior: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        payload = _row_payload(row)
        if payload.get("status") != "complete":
            continue
        if str(payload.get("generated_at") or "") == current_generated_at:
            continue
        score = _payload_score(payload)
        if score is None:
            continue
        prior.append({
            "generated_at": _generated_at(row),
            "score": score,
            "workflow": row.get("workflow") or "express",
            "repository": payload.get("repository") or payload.get("source_scope") or "",
        })
    prior.sort(key=lambda item: item.get("generated_at") or "")
    prior_scores = [item["score"] for item in prior]
    previous_score = prior_scores[-1] if prior_scores else None
    average_prior = round(sum(prior_scores) / len(prior_scores)) if prior_scores else None
    delta_from_previous = current_score - previous_score if current_score is not None and previous_score is not None else None
    delta_from_average = current_score - average_prior if current_score is not None and average_prior is not None else None
    if len(prior_scores) >= 2:
        trend_status = "tracked"
    elif len(prior_scores) == 1:
        trend_status = "baseline"
    else:
        trend_status = "unavailable"
    non_regressing = bool(
        current_score is not None
        and previous_score is not None
        and average_prior is not None
        and current_score >= previous_score
        and current_score >= average_prior
    )
    notes: list[str] = []
    if trend_status == "tracked":
        notes.append(
            f"Project trend evidence: {len(prior_scores)} prior completed Express run(s); previous score={previous_score}; prior average={average_prior}; current score={current_score}; delta vs previous={delta_from_previous}."
        )
    elif trend_status == "baseline":
        notes.append(
            f"Project trend baseline: 1 prior completed Express run; previous score={previous_score}; current score={current_score}. More runs are needed for a stable trend."
        )
    else:
        notes.append("Project trend unavailable: no prior completed Express runs were found for this project in retained storage.")
    return {
        "status": trend_status,
        "project_id": resolved_project_id,
        "source": STORE.status().get("adapter", "memory"),
        "current_score": current_score,
        "prior_run_count": len(prior_scores),
        "previous_score": previous_score,
        "average_prior_score": average_prior,
        "delta_from_previous": delta_from_previous,
        "delta_from_average": delta_from_average,
        "non_regressing": non_regressing,
        "recent_scores": prior_scores[-5:],
        "notes": notes,
        "rule": "Trend evidence can support Work-vs-Expected only after retained prior completed runs exist for the same project.",
    }


def apply_project_trend_evidence(result: dict[str, Any]) -> dict[str, Any]:
    trend = project_trend_evidence(result)
    result["project_trend_evidence"] = trend
    velocity = next((item for item in result.get("sections", []) or [] if isinstance(item, dict) and item.get("id") == "velocity_complexity"), None)
    if velocity is None:
        return result
    velocity.setdefault("evidence", [])
    for note in trend.get("notes", []):
        if note not in velocity["evidence"]:
            velocity["evidence"].append(note)
    release_status = (result.get("release_readiness") or {}).get("status")
    if trend.get("status") == "tracked" and trend.get("non_regressing") and release_status == "provisionally_ready_for_human_review":
        velocity["score"] = max(int(velocity.get("score") or 0), 94)
        velocity["status"] = "green"
        velocity["summary"] = "Work-vs-expected signal uses velocity, PR traceability, source footprint, release-readiness evidence, and retained non-regressing project trend history."
        extra = "Retained project history supports Work-vs-Expected: the current score is non-regressing versus both the previous retained run and prior average."
        if extra not in velocity["evidence"]:
            velocity["evidence"].append(extra)
    return result
