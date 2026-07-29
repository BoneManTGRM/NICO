from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

VERSION = "nico.phase15.finding-quality.v1"

_SEVERITY = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_LIKELIHOOD = {"certain": 4, "likely": 3, "possible": 2, "unlikely": 1, "unknown": 0}
_CONFIDENCE = {"high": 3, "medium": 2, "low": 1, "unknown": 0}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _norm(value: Any) -> str:
    return _text(value).casefold()


def _score(item: Mapping[str, Any]) -> int:
    severity = _SEVERITY.get(_norm(item.get("severity")), 0)
    likelihood = _LIKELIHOOD.get(_norm(item.get("likelihood")), 0)
    confidence = _CONFIDENCE.get(_norm(item.get("confidence")), 0)
    impact = 2 if _text(item.get("business_impact")) else 0
    release_blocking = 4 if item.get("release_blocking") is True else 0
    return severity * 4 + likelihood * 2 + confidence + impact + release_blocking


def _priority(item: Mapping[str, Any]) -> str:
    score = _score(item)
    severe = _norm(item.get("severity")) in {"critical", "high"}
    material = bool(_text(item.get("business_impact")))
    if item.get("release_blocking") is True or (score >= 21 and severe and material):
        return "P1"
    if score >= 13:
        return "P2"
    return "P3"


def _ranking_reason(item: Mapping[str, Any], priority: str) -> str:
    parts = [
        f"severity={_norm(item.get('severity')) or 'unknown'}",
        f"likelihood={_norm(item.get('likelihood')) or 'unknown'}",
        f"confidence={_norm(item.get('confidence')) or 'unknown'}",
    ]
    if item.get("release_blocking") is True:
        parts.append("release-blocking")
    if _text(item.get("business_impact")):
        parts.append("material business impact")
    return f"{priority} because " + ", ".join(parts) + "."


def quality_finding(item: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(item))
    required = ("severity", "likelihood", "confidence", "business_impact")
    missing = [key for key in required if not _text(result.get(key))]
    priority = _priority(result) if not missing else "P3"
    result["priority"] = priority
    result["ranking_score"] = _score(result)
    result["ranking_reason"] = _ranking_reason(result, priority)
    result["quality_complete"] = not missing
    result["quality_gaps"] = missing
    result["fact"] = _text(result.get("fact") or result.get("evidence"))
    result["interpretation"] = _text(result.get("interpretation"))
    result["inference"] = _text(result.get("inference"))
    result["recommendation"] = _text(result.get("recommendation"))
    result["owner_role"] = _text(result.get("owner_role") or "Engineering owner")
    result["effort"] = _text(result.get("effort") or "TBD")
    result["residual_risk"] = _text(result.get("residual_risk") or "TBD")
    criteria = result.get("acceptance_criteria")
    if isinstance(criteria, str):
        criteria = [criteria]
    result["acceptance_criteria"] = [
        _text(value) for value in (criteria or []) if _text(value)
    ]
    return result


def prioritize_findings(findings: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    prepared = [quality_finding(item) for item in findings]
    prepared.sort(key=lambda item: (-item["ranking_score"], _norm(item.get("title")), _norm(item.get("finding_id"))))
    top5 = prepared[:5]
    next10 = prepared[5:15]
    backlog = prepared[15:]
    return {
        "schema": VERSION,
        "top_5": top5,
        "next_10": next10,
        "backlog": backlog,
        "all_findings": prepared,
        "generic_title_collision": len({_norm(item.get("title")) for item in top5}) != len(top5),
    }


__all__ = ["VERSION", "quality_finding", "prioritize_findings"]
