from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any

from nico import comprehensive_human_evidence_report_v1 as v1

VERSION = "nico.comprehensive_human_evidence_report.v2"
# The decision-grade report path keeps only 18 evidence lines per stage after its own
# normalization. Keep a margin so every explicit client-supplied line survives intact.
_BASE_STAGE_EVIDENCE_LIMIT = 16


def _literal_mapping(lines: list[str]) -> dict[str, str]:
    """Preserve literal report lines through the base stage flattener without prefixes."""

    output: dict[str, str] = {}
    for index, raw in enumerate(lines, start=1):
        line = str(raw or "").strip()
        if not line:
            continue
        if ": " in line:
            label, value = line.split(": ", 1)
        else:
            label, value = f"Client-supplied data {index}", line
        key = label
        suffix = 2
        while key in output:
            key = f"{label} [{suffix}]"
            suffix += 1
        output[key] = value
    return output


def _canonical_injection_specs(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Create bounded English source stages for the ordinary canonical report builder.

    The established decision-grade renderer keeps at most 18 evidence records per stage.
    The durable human-evidence package can contain more, so collapse the v1 presentation
    specs back to each module and rechunk at 16. Later premium locale projection can then
    translate NICO-owned labels without rerunning the assessment or losing client input.
    """

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in v1._human_module_stage_specs(snapshot, spanish=False):
        grouped[v1._module_id_from_stage(str(spec.get("stage_id") or ""))].append(spec)

    output: list[dict[str, Any]] = []
    for module_id, source_specs in grouped.items():
        lines = [
            str(line)
            for spec in source_specs
            for line in spec.get("evidence") or []
            if str(line).strip()
        ]
        if not lines:
            continue
        chunks = [
            lines[index : index + _BASE_STAGE_EVIDENCE_LIMIT]
            for index in range(0, len(lines), _BASE_STAGE_EVIDENCE_LIMIT)
        ]
        first = source_specs[0]
        clean_title = re.sub(
            r"\s*\(\d+/\d+\)\s*$",
            "",
            str(first.get("title") or "").strip(),
        )
        for index, chunk in enumerate(chunks, start=1):
            suffix = f" ({index}/{len(chunks)})" if len(chunks) > 1 else ""
            output.append(
                {
                    "stage_id": (
                        f"client_human_evidence_{module_id}"
                        + (f"_{index}" if len(chunks) > 1 else "")
                    ),
                    "title": f"{clean_title}{suffix}",
                    "summary": str(first.get("summary") or ""),
                    "evidence": chunk,
                    "findings": [],
                    "unavailable": [],
                    "status": "complete",
                }
            )
    return output


def _has_verified_human_context(snapshot: Mapping[str, Any]) -> bool:
    display = snapshot.get("display_values")
    if isinstance(display, Mapping) and any(
        str(value or "").strip() for value in display.values()
    ):
        return True
    package = snapshot.get("human_evidence")
    return isinstance(package, Mapping) and bool(package.get("provided_module_ids"))


def _inject_human_review_stages(
    stage_results: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    # The existing stage payload can be large. A shallow container copy is sufficient
    # because the function only adds new report-only keys and never mutates prior values.
    output = dict(stage_results)
    if not _has_verified_human_context(snapshot):
        return output

    summary = v1._client_summary_stage(snapshot, spanish=False)
    specs = [summary, *_canonical_injection_specs(snapshot)]
    for spec in specs:
        stage_id = str(spec.get("stage_id") or "").strip()
        if not stage_id:
            continue
        output[stage_id] = {
            "status": str(spec.get("status") or "complete"),
            "summary": str(spec.get("summary") or ""),
            # A mapping lets the established base flattener emit the human literal
            # exactly once instead of prefixing list ordinals such as "1: ...".
            "evidence": _literal_mapping(list(spec.get("evidence") or [])),
            "findings": list(spec.get("findings") or []),
            "unavailable": list(spec.get("unavailable") or []),
        }
    return output


def _install_english_retained_titles() -> dict[str, bool]:
    current = v1._localize_retained_stage
    if getattr(current, "_nico_human_evidence_retained_titles_v2", False):
        return {"english_human_stage_titles_normalized": True}
    original = current

    def localize_retained_stage(
        stage: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> dict[str, Any]:
        output = original(stage, spanish=spanish)
        if spanish:
            return output
        stage_id = v1._text(output.get("stage_id"), 180)
        if stage_id == "client_evidence_summary":
            output["title"] = "Client Evidence Summary"
            output["summary"] = (
                "Client-supplied engagement metadata and human-observed evidence are "
                "retained as explicit review context. Missing facts are not inferred. "
                "These values do not change technical scores or grant approval or "
                "delivery authority."
            )
        elif stage_id.startswith("client_human_evidence_"):
            module_id = v1._module_id_from_stage(stage_id)
            from nico.strategic_human_evidence_v1 import MODULES

            definition = MODULES.get(module_id) or {}
            label = str(definition.get("label") or "").strip()
            if not label:
                label = module_id.replace("_", " ").title()
            output["title"] = f"Client Human Evidence — {label}"
            output["summary"] = (
                "These observations were explicitly supplied by people and are retained "
                "without repository inference. They do not automatically change technical "
                "scores or grant approval or delivery authority."
            )
        return output

    localize_retained_stage._nico_human_evidence_retained_titles_v2 = True
    v1._localize_retained_stage = localize_retained_stage
    return {"english_human_stage_titles_normalized": True}


def install_comprehensive_human_evidence_report_v2() -> dict[str, Any]:
    state = dict(v1.install_comprehensive_human_evidence_report_v1())
    state.update(
        {
            "status": "installed",
            "version": VERSION,
            **_install_english_retained_titles(),
            "base_canonical_stage_injection_bound": True,
            "base_stage_evidence_limit_respected": True,
            "all_verified_human_modules_projected": True,
            "engagement_metadata_five_field_projection": True,
            "verified_durable_human_evidence_only": True,
            "repository_inference_prohibited": True,
            "technical_scores_unchanged": True,
            "canonical_scope_ids_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return state


def build_report_package_with_human_context(
    builder: Callable[..., dict[str, Any]],
    *,
    context: Mapping[str, Any],
    identity: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the established package with verified human input retained end to end.

    This function does not create an alternate assessment. It adds bounded report-only
    human-context stages to the exact canonical stage population before the existing
    builder runs, while also binding the locale-aware premium projection for any rebuild
    in the same call. Only digest-verified explicit input is projected; missing values are
    never inferred, and scores, findings, approval, and delivery authority remain owned by
    their existing canonical sources.
    """

    install_comprehensive_human_evidence_report_v2()
    snapshot = v1._context_snapshot(context)
    stages = _inject_human_review_stages(stage_results, snapshot)
    token = v1._REPORT_CONTEXT.set(snapshot)
    try:
        return builder(identity=identity, stage_results=stages)
    finally:
        v1._REPORT_CONTEXT.reset(token)


__all__ = [
    "VERSION",
    "build_report_package_with_human_context",
    "install_comprehensive_human_evidence_report_v2",
]
