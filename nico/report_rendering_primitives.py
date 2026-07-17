from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from nico.report_design_system import NICO_REPORT_DESIGN_SYSTEM


@dataclass(frozen=True)
class ExecutiveMetric:
    label: str
    value: str
    context: str = ""
    tone: str = "neutral"


@dataclass(frozen=True)
class EvidenceCard:
    evidence_id: str
    source: str
    analyzer: str
    snapshot: str
    confidence: str
    acceptance: str
    disposition: str
    fingerprint: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class RepairAction:
    priority: str
    title: str
    business_impact: str
    technical_action: str
    owner: str
    effort: str
    verification: str
    rollback: str
    conditional_score_impact: str = ""


_ALLOWED_TONES = {"neutral", "success", "warning", "danger", "accent"}


def _text(value: Any, *, empty: str = "Not provided") -> str:
    if value is None:
        return empty
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = " ".join(str(value).split())
    return text or empty


def normalize_metrics(items: Iterable[Mapping[str, Any] | ExecutiveMetric]) -> tuple[ExecutiveMetric, ...]:
    output: list[ExecutiveMetric] = []
    seen: set[str] = set()
    for item in items:
        metric = item if isinstance(item, ExecutiveMetric) else ExecutiveMetric(
            label=_text(item.get("label")),
            value=_text(item.get("value")),
            context=_text(item.get("context"), empty=""),
            tone=_text(item.get("tone"), empty="neutral").lower(),
        )
        key = metric.label.casefold()
        if key in seen:
            continue
        seen.add(key)
        tone = metric.tone if metric.tone in _ALLOWED_TONES else "neutral"
        output.append(ExecutiveMetric(metric.label, metric.value, metric.context, tone))
    return tuple(output)


def normalize_evidence_cards(items: Iterable[Mapping[str, Any] | EvidenceCard]) -> tuple[EvidenceCard, ...]:
    output: list[EvidenceCard] = []
    seen: set[str] = set()
    for item in items:
        card = item if isinstance(item, EvidenceCard) else EvidenceCard(
            evidence_id=_text(item.get("evidence_id") or item.get("id")),
            source=_text(item.get("source")),
            analyzer=_text(item.get("analyzer")),
            snapshot=_text(item.get("snapshot") or item.get("snapshot_commit_sha")),
            confidence=_text(item.get("confidence")),
            acceptance=_text(item.get("acceptance") or item.get("scoring_acceptance")),
            disposition=_text(item.get("disposition")),
            fingerprint=_text(item.get("fingerprint") or item.get("hash"), empty=""),
            timestamp=_text(item.get("timestamp"), empty=""),
        )
        key = card.evidence_id.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(card)
    return tuple(output)


def normalize_repair_actions(items: Iterable[Mapping[str, Any] | RepairAction]) -> tuple[RepairAction, ...]:
    output: list[RepairAction] = []
    seen: set[str] = set()
    for index, item in enumerate(items, 1):
        action = item if isinstance(item, RepairAction) else RepairAction(
            priority=_text(item.get("priority"), empty=f"P{index}"),
            title=_text(item.get("title") or item.get("label")),
            business_impact=_text(item.get("business_impact") or item.get("impact")),
            technical_action=_text(item.get("technical_action") or item.get("action")),
            owner=_text(item.get("owner")),
            effort=_text(item.get("effort")),
            verification=_text(item.get("verification")),
            rollback=_text(item.get("rollback"), empty="Document the smallest reversible fallback before implementation."),
            conditional_score_impact=_text(item.get("conditional_score_impact"), empty=""),
        )
        key = action.title.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(action)
    return tuple(output)


def validate_rendering_payload(
    *,
    metrics: Sequence[ExecutiveMetric],
    evidence_cards: Sequence[EvidenceCard],
    repair_actions: Sequence[RepairAction],
) -> list[str]:
    issues: list[str] = []
    if len(metrics) < 4:
        issues.append("executive_dashboard_requires_at_least_four_metrics")
    if not evidence_cards:
        issues.append("evidence_cards_required")
    for card in evidence_cards:
        if card.evidence_id == "Not provided":
            issues.append("evidence_id_required")
        if card.snapshot == "Not provided":
            issues.append(f"evidence_snapshot_required:{card.evidence_id}")
        if card.acceptance == "Not provided":
            issues.append(f"evidence_acceptance_required:{card.evidence_id}")
    if not repair_actions:
        issues.append("repair_actions_required")
    for action in repair_actions:
        if action.verification == "Not provided":
            issues.append(f"repair_verification_required:{action.title}")
        if action.rollback == "Not provided":
            issues.append(f"repair_rollback_required:{action.title}")
    return issues


def reportlab_style_tokens() -> dict[str, Any]:
    """Return renderer-neutral values derived from the canonical design system.

    ReportLab modules can consume these values without duplicating typography,
    spacing, or palette constants. The function intentionally returns primitive
    values so importing this module does not require ReportLab at startup.
    """
    system = NICO_REPORT_DESIGN_SYSTEM
    return {
        "version": system.version,
        "palette": vars(system.palette).copy(),
        "typography": vars(system.typography).copy(),
        "layout": vars(system.layout).copy(),
        "required_components": tuple(system.required_components),
    }


__all__ = [
    "EvidenceCard",
    "ExecutiveMetric",
    "RepairAction",
    "normalize_evidence_cards",
    "normalize_metrics",
    "normalize_repair_actions",
    "reportlab_style_tokens",
    "validate_rendering_payload",
]
