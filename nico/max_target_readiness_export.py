from __future__ import annotations

from typing import Any

from nico.max_target_readiness_packet import build_max_target_readiness_packet


def _line_items(values: list[Any]) -> list[str]:
    return [f"- {value}" for value in values]


def build_max_target_readiness_markdown(payload: dict[str, Any]) -> str:
    packet = build_max_target_readiness_packet(payload or {})
    lines = [
        "# NICO Max Target Readiness",
        "",
        f"Status: {packet.get('status')}",
        f"Overall score: {packet.get('overall_score')} / {packet.get('overall_target')}",
        f"Overall gap: {packet.get('overall_gap')}",
        f"Ready for all max targets: {packet.get('ready_for_all_max')}",
        "",
        "## Service cards",
    ]
    for card in packet.get("service_cards") or []:
        lines.append(
            f"- {card.get('service')}: {card.get('score')} / {card.get('target')} "
            f"(gap {card.get('gap')}, missing {card.get('missing_count')}, ready {card.get('ready')})"
        )
    lines.extend(["", "## Next actions"])
    steps = packet.get("steps") or []
    if steps:
        for step in steps:
            lines.append(f"{step.get('order')}. [{step.get('service_label')}] {step.get('gate')}: {step.get('action')}")
    else:
        lines.append("No remaining action steps.")
    lines.extend(["", "## Delivery items"])
    lines.extend(_line_items(packet.get("delivery_items") or []))
    lines.extend(["", "## Disclosures"])
    lines.extend(_line_items(packet.get("disclosures") or []))
    lines.extend(["", "## Summary", str(packet.get("client_summary") or "")])
    return "\n".join(lines).strip() + "\n"


def build_max_target_readiness_export(payload: dict[str, Any], export_format: str = "markdown") -> dict[str, Any]:
    packet = build_max_target_readiness_packet(payload or {})
    fmt = (export_format or "markdown").lower()
    if fmt == "json":
        return {"status": "ok", "format": "json", "content": packet}
    if fmt == "markdown":
        return {"status": "ok", "format": "markdown", "content": build_max_target_readiness_markdown(payload or {})}
    return {"status": "unsupported", "format": fmt, "content": "", "supported_formats": ["json", "markdown"]}
