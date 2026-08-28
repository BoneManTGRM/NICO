from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

VERSION = "nico.comprehensive_human_evidence_report.v1"

_CLIENT_LITERAL_EN_PREFIX = "Client-supplied data · "
_CLIENT_LITERAL_ES_PREFIX = "Dato aportado por el cliente · "
_REPORT_LINE_CHARS = 760
# The established decision-grade stage summarizer retains at most 18 evidence lines
# per stage. Stay below that boundary so explicit human input is never silently clipped.
_REPORT_STAGE_LINES = 16

_REPORT_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "nico_comprehensive_human_evidence_report_context",
    default={},
)

_MODULE_LABEL_ES = {
    "functional_qa": "QA funcional",
    "platform_parity": "Paridad de navegador, dispositivo y plataforma",
    "accessibility_ux": "Revisión de accesibilidad y UX",
    "stakeholder_context": "Objetivos y restricciones de las partes interesadas",
    "incident_history": "Historial de incidentes y soporte",
    "product_objectives": "Objetivos del producto y resultados de la publicación",
    "release_constraints": "Plazos de publicación y restricciones de entrega",
    "compliance_requirements": "Requisitos regulatorios y contractuales",
    "budget_staffing": "Restricciones de presupuesto, personal y capacidad",
    "accepted_risks": "Decisiones conocidas y riesgos aceptados",
}
_FIELD_LABELS = {
    "test_cases": ("Test cases", "Casos de prueba"),
    "observed_results": ("Observed results", "Resultados observados"),
    "matrix": ("Matrix", "Matriz"),
    "observations": ("Observations", "Observaciones"),
    "objectives": ("Objectives", "Objetivos"),
    "constraints": ("Constraints", "Restricciones"),
    "incidents": ("Incidents", "Incidentes"),
    "success_measures": ("Success measures", "Medidas de éxito"),
    "requirements": ("Requirements", "Requisitos"),
    "decisions": ("Decisions", "Decisiones"),
    "access_method": ("Access method", "Método de acceso"),
    "primary_technical_contact": (
        "Primary technical contact",
        "Contacto técnico principal",
    ),
    "authorized_scope": ("Authorized scope", "Alcance autorizado"),
    "reviewer": ("Reviewer", "Revisor"),
    "observed_at": ("Observed at", "Fecha de observación"),
    "source_reference": ("Source reference", "Referencia de fuente"),
    "exclusion_rationale": ("Exclusion rationale", "Justificación de exclusión"),
}
_ENGAGEMENT_LABELS = {
    "customer_name": ("Client display name", "Nombre mostrado del cliente"),
    "project_name": ("Project display name", "Nombre mostrado del proyecto"),
    "primary_technical_contact": (
        "Primary technical contact",
        "Contacto técnico principal",
    ),
    "access_method": ("Access method", "Método de acceso"),
    "authorized_scope": ("Authorized scope", "Alcance autorizado"),
}
_EN_TO_ES_LABELS = {
    english: spanish
    for english, spanish in (
        *tuple(_FIELD_LABELS.values()),
        *tuple(_ENGAGEMENT_LABELS.values()),
        ("Excluded from scope", "Excluido del alcance"),
    )
}


def _text(value: Any, limit: int = 500) -> str:
    normalized = " ".join(
        str(value if value is not None else "").split()
    ).strip()
    return (
        normalized
        if len(normalized) <= limit
        else normalized[: max(0, limit - 3)].rstrip() + "..."
    )


def _verified_engagement(value: Any) -> dict[str, Any]:
    from nico.comprehensive_engagement_metadata_v1 import (
        normalize_comprehensive_engagement_metadata,
        verify_comprehensive_engagement_metadata,
    )

    if not verify_comprehensive_engagement_metadata(value):
        return {}
    return normalize_comprehensive_engagement_metadata(value)


def _verified_human_evidence(value: Any) -> dict[str, Any]:
    from nico.strategic_human_evidence_v1 import verify_strategic_human_evidence

    if not isinstance(value, Mapping):
        return {}
    if not verify_strategic_human_evidence(value):
        return {}
    return deepcopy(dict(value))


def _context_snapshot(context: Mapping[str, Any]) -> dict[str, Any]:
    engagement = _verified_engagement(context.get("engagement_metadata"))
    display_values = {
        "customer_name": _text(
            engagement.get("client_name") or context.get("customer_name"),
            180,
        ),
        "project_name": _text(
            engagement.get("project_name") or context.get("project_name"),
            180,
        ),
        "primary_technical_contact": _text(
            engagement.get("primary_technical_contact")
            or context.get("primary_technical_contact"),
            600,
        ),
        "access_method": _text(
            engagement.get("access_method") or context.get("access_method"),
            1200,
        ),
        "authorized_scope": _text(
            engagement.get("authorized_scope") or context.get("authorized_scope"),
            4000,
        ),
    }
    return {
        "report_language": _text(context.get("report_language"), 40) or "en",
        "display_values": display_values,
        "human_evidence": _verified_human_evidence(context.get("human_evidence")),
    }


def build_report_package_with_human_context(
    builder: Callable[..., dict[str, Any]],
    *,
    context: Mapping[str, Any],
    identity: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Run the established report builder with verified human context in scope.

    The context variable never becomes independent report truth. It is populated from
    the exact durable run context immediately before the existing final renderer runs
    and is reset afterward. The canonical report receives only explicit, verified
    client-supplied values; technical scores, findings, approval state, and delivery
    authority remain owned by their existing canonical sources.
    """

    install_comprehensive_human_evidence_report_v1()
    token = _REPORT_CONTEXT.set(_context_snapshot(context))
    try:
        return builder(identity=identity, stage_results=stage_results)
    finally:
        _REPORT_CONTEXT.reset(token)


def _split_text(value: Any, limit: int = _REPORT_LINE_CHARS) -> list[str]:
    text = _text(value, 100_000)
    if not text:
        return []
    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind(" ", 0, limit + 1)
        if split_at < max(40, limit // 3):
            split_at = limit
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def _literal_lines(
    label: str,
    value: Any,
    *,
    spanish: bool,
) -> list[str]:
    prefix = _CLIENT_LITERAL_ES_PREFIX if spanish else _CLIENT_LITERAL_EN_PREFIX
    pieces = _split_text(value)
    if not pieces:
        return []
    if len(pieces) == 1:
        return [f"{prefix}{label}: {pieces[0]}"]
    part_word = "parte" if spanish else "part"
    return [
        f"{prefix}{label} ({part_word} {index}/{len(pieces)}): {piece}"
        for index, piece in enumerate(pieces, start=1)
    ]


def _flatten_scalars(value: Any, path: str = "") -> list[tuple[str, str]]:
    if isinstance(value, Mapping):
        output: list[tuple[str, str]] = []
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            output.extend(_flatten_scalars(item, child))
        return output
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        output = []
        for index, item in enumerate(value, start=1):
            child = f"{path}[{index}]" if path else f"[{index}]"
            output.extend(_flatten_scalars(item, child))
        return output
    normalized = _text(value, 100_000)
    return [(path, normalized)] if normalized else []


def _field_path_label(path: str, *, spanish: bool) -> str:
    root = path
    suffix = ""
    for token in (".", "["):
        index = root.find(token)
        if index >= 0:
            suffix = root[index:]
            root = root[:index]
            break
    labels = _FIELD_LABELS.get(
        root,
        (root.replace("_", " ").title(), root.replace("_", " ").title()),
    )
    return f"{labels[1 if spanish else 0]}{suffix}"


def _engagement_lines(
    snapshot: Mapping[str, Any],
    *,
    spanish: bool,
) -> tuple[list[str], list[str]]:
    values = (
        snapshot.get("display_values")
        if isinstance(snapshot.get("display_values"), Mapping)
        else {}
    )
    evidence: list[str] = []
    missing: list[str] = []
    for key, labels in _ENGAGEMENT_LABELS.items():
        label = labels[1 if spanish else 0]
        value = values.get(key)
        if _text(value, 4000):
            evidence.extend(_literal_lines(label, value, spanish=spanish))
        else:
            missing.append(
                f"{label}: {'no proporcionado' if spanish else 'not supplied'}"
            )
    return evidence, missing


def _human_module_stage_specs(
    snapshot: Mapping[str, Any],
    *,
    spanish: bool,
) -> list[dict[str, Any]]:
    package = (
        snapshot.get("human_evidence")
        if isinstance(snapshot.get("human_evidence"), Mapping)
        else {}
    )
    modules = (
        package.get("modules")
        if isinstance(package.get("modules"), Mapping)
        else {}
    )
    provided = [
        str(module_id)
        for module_id in package.get("provided_module_ids") or []
        if str(module_id) in modules
    ]
    specs: list[dict[str, Any]] = []
    for module_id in provided:
        module = modules.get(module_id)
        if not isinstance(module, Mapping):
            continue
        source_label = (
            _text(module.get("label"), 240)
            or module_id.replace("_", " ").title()
        )
        module_label = (
            _MODULE_LABEL_ES.get(module_id, source_label)
            if spanish
            else source_label
        )
        lines: list[str] = []

        evidence = (
            module.get("evidence")
            if isinstance(module.get("evidence"), Mapping)
            else {}
        )
        for field, raw in evidence.items():
            for path, scalar in _flatten_scalars(raw, str(field)):
                lines.extend(
                    _literal_lines(
                        _field_path_label(path, spanish=spanish),
                        scalar,
                        spanish=spanish,
                    )
                )

        for field in ("reviewer", "observed_at", "source_reference"):
            value = module.get(field)
            if _text(value, 10_000):
                labels = _FIELD_LABELS[field]
                lines.extend(
                    _literal_lines(
                        labels[1 if spanish else 0],
                        value,
                        spanish=spanish,
                    )
                )

        if module.get("excluded") is True:
            lines.extend(
                _literal_lines(
                    "Excluido del alcance"
                    if spanish
                    else "Excluded from scope",
                    "Sí" if spanish else "Yes",
                    spanish=spanish,
                )
            )
        rationale = module.get("exclusion_rationale")
        if _text(rationale, 10_000):
            labels = _FIELD_LABELS["exclusion_rationale"]
            lines.extend(
                _literal_lines(
                    labels[1 if spanish else 0],
                    rationale,
                    spanish=spanish,
                )
            )

        if not lines:
            continue

        chunks = [
            lines[index : index + _REPORT_STAGE_LINES]
            for index in range(0, len(lines), _REPORT_STAGE_LINES)
        ]
        for index, chunk in enumerate(chunks, start=1):
            chunk_suffix = (
                f" ({index}/{len(chunks)})"
                if len(chunks) > 1
                else ""
            )
            specs.append(
                {
                    "stage_id": (
                        f"client_human_evidence_{module_id}"
                        + (
                            f"_{index}"
                            if len(chunks) > 1
                            else ""
                        )
                    ),
                    "title": (
                        "Evidencia humana aportada por el cliente — "
                        f"{module_label}{chunk_suffix}"
                        if spanish
                        else "Client Human Evidence — "
                        f"{module_label}{chunk_suffix}"
                    ),
                    "summary": (
                        "Estas observaciones fueron aportadas explícitamente por "
                        "personas y se conservan sin inferencias del repositorio. "
                        "No modifican automáticamente las puntuaciones técnicas ni "
                        "conceden aprobación o autoridad de entrega."
                        if spanish
                        else "These observations were explicitly supplied by people "
                        "and are retained without repository inference. They do not "
                        "automatically change technical scores or grant approval or "
                        "delivery authority."
                    ),
                    "evidence": chunk,
                    "findings": [],
                    "unavailable": [],
                    "status": "complete",
                }
            )
    return specs


def _client_summary_stage(
    snapshot: Mapping[str, Any],
    *,
    spanish: bool,
) -> dict[str, Any]:
    evidence, missing = _engagement_lines(snapshot, spanish=spanish)
    return {
        "stage_id": "client_evidence_summary",
        "title": (
            "Resumen de evidencia del cliente"
            if spanish
            else "Client Evidence Summary"
        ),
        "summary": (
            "Los metadatos del encargo aportados por el cliente y la evidencia "
            "observada por personas se conservan como contexto explícito de "
            "revisión. Los datos faltantes no se infieren. Estos valores no "
            "modifican las puntuaciones técnicas ni conceden aprobación o "
            "autoridad de entrega."
            if spanish
            else "Client-supplied engagement metadata and human-observed evidence "
            "are retained as explicit review context. Missing facts are not "
            "inferred. These values do not change technical scores or grant "
            "approval or delivery authority."
        ),
        "evidence": evidence,
        "findings": [],
        "unavailable": missing,
        "status": "complete" if evidence else "review_required",
    }


def _retained_human_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = canonical.get("stage_summaries")
    if not isinstance(values, Sequence) or isinstance(
        values,
        (str, bytes, bytearray),
    ):
        return []
    output: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, Mapping):
            continue
        stage_id = _text(item.get("stage_id"), 180)
        if stage_id == "client_evidence_summary" or stage_id.startswith(
            "client_human_evidence_"
        ):
            output.append(deepcopy(dict(item)))
    return output


def _translate_client_literal_line(value: Any) -> str:
    text = str(value or "")
    stripped = text.strip()
    if stripped.startswith(_CLIENT_LITERAL_ES_PREFIX):
        return text
    if not stripped.startswith(_CLIENT_LITERAL_EN_PREFIX):
        return text

    body = stripped[len(_CLIENT_LITERAL_EN_PREFIX) :]
    if ": " not in body:
        return (
            _CLIENT_LITERAL_ES_PREFIX
            + body.replace(" (part ", " (parte ")
        )
    label, supplied = body.split(": ", 1)
    translated = label
    for english, spanish in sorted(
        _EN_TO_ES_LABELS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if translated.startswith(english):
            translated = spanish + translated[len(english) :]
            break
    translated = translated.replace(" (part ", " (parte ")
    return f"{_CLIENT_LITERAL_ES_PREFIX}{translated}: {supplied}"


def _module_id_from_stage(stage_id: str) -> str:
    suffix = stage_id.removeprefix("client_human_evidence_")
    if suffix.rsplit("_", 1)[-1].isdigit():
        suffix = suffix.rsplit("_", 1)[0]
    return suffix


def _localize_retained_stage(
    stage: Mapping[str, Any],
    *,
    spanish: bool,
) -> dict[str, Any]:
    output = deepcopy(dict(stage))
    if not spanish:
        return output
    stage_id = _text(output.get("stage_id"), 180)
    if stage_id == "client_evidence_summary":
        output["title"] = "Resumen de evidencia del cliente"
        output["summary"] = (
            "Los metadatos del encargo aportados por el cliente y la evidencia "
            "observada por personas se conservan como contexto explícito de "
            "revisión. Los datos faltantes no se infieren. Estos valores no "
            "modifican las puntuaciones técnicas ni conceden aprobación o "
            "autoridad de entrega."
        )
        localized_missing: list[str] = []
        for raw in output.get("unavailable") or []:
            line = str(raw or "")
            for labels in _ENGAGEMENT_LABELS.values():
                english, translated = labels
                if line.startswith(f"{english}:"):
                    line = (
                        f"{translated}: no proporcionado"
                        if "not supplied" in line.casefold()
                        else f"{translated}:{line.split(':', 1)[1]}"
                    )
                    break
            localized_missing.append(line)
        output["unavailable"] = localized_missing
    elif stage_id.startswith("client_human_evidence_"):
        module_id = _module_id_from_stage(stage_id)
        label = _MODULE_LABEL_ES.get(
            module_id,
            module_id.replace("_", " ").title(),
        )
        original_title = _text(output.get("title"), 300)
        chunk_suffix = ""
        if original_title.endswith(")") and " (" in original_title:
            candidate = original_title[original_title.rfind(" (") :]
            if "/" in candidate:
                chunk_suffix = candidate
        output["title"] = (
            "Evidencia humana aportada por el cliente — "
            f"{label}{chunk_suffix}"
        )
        output["summary"] = (
            "Estas observaciones fueron aportadas explícitamente por personas "
            "y se conservan sin inferencias del repositorio. No modifican "
            "automáticamente las puntuaciones técnicas ni conceden aprobación "
            "o autoridad de entrega."
        )
    output["evidence"] = [
        _translate_client_literal_line(item)
        for item in output.get("evidence") or []
    ]
    return output


def _install_renderer_projection() -> dict[str, bool]:
    import nico.v2_premium_report_renderer as renderer

    current = renderer._canonical_stages
    if getattr(current, "_nico_full_human_evidence_v1", False):
        return {
            "renderer_human_evidence_projection_bound": True,
            "all_verified_human_modules_projected": True,
            "engagement_metadata_five_field_projection": True,
        }
    original = current

    def canonical_stages_with_human_evidence(canonical):
        retained = _retained_human_stages(canonical)
        stages = [deepcopy(dict(item)) for item in original(canonical)]
        spanish = renderer._is_spanish(canonical)
        snapshot = dict(_REPORT_CONTEXT.get() or {})

        def upsert(stage: Mapping[str, Any]) -> None:
            candidate = deepcopy(dict(stage))
            target_id = _text(candidate.get("stage_id"), 180)
            for index, existing in enumerate(stages):
                if _text(existing.get("stage_id"), 180) == target_id:
                    stages[index] = candidate
                    return
            stages.append(candidate)

        if snapshot:
            upsert(_client_summary_stage(snapshot, spanish=spanish))
            for spec in _human_module_stage_specs(snapshot, spanish=spanish):
                upsert(spec)
        else:
            for stage in retained:
                upsert(_localize_retained_stage(stage, spanish=spanish))
        return stages

    canonical_stages_with_human_evidence._nico_full_human_evidence_v1 = True
    renderer._canonical_stages = canonical_stages_with_human_evidence
    return {
        "renderer_human_evidence_projection_bound": True,
        "all_verified_human_modules_projected": True,
        "engagement_metadata_five_field_projection": True,
    }


def _install_spanish_literal_guard() -> dict[str, bool]:
    import nico.comprehensive_spanish_canonical_report_v87 as canonical

    current = canonical._translate_presentation_field
    if getattr(current, "_nico_client_literal_guard_v1", False):
        return {
            "spanish_client_supplied_literals_preserved": True,
            "spanish_nico_authored_prose_still_fail_closed": True,
        }
    original = current

    def translate_with_client_literal_guard(value: str, key: str) -> str:
        stripped = str(value or "").strip()
        if key == "evidence" and stripped.startswith(_CLIENT_LITERAL_ES_PREFIX):
            return str(value)
        if key == "evidence" and stripped.startswith(_CLIENT_LITERAL_EN_PREFIX):
            return _translate_client_literal_line(value)
        return original(value, key)

    translate_with_client_literal_guard._nico_client_literal_guard_v1 = True
    canonical._translate_presentation_field = translate_with_client_literal_guard
    return {
        "spanish_client_supplied_literals_preserved": True,
        "spanish_nico_authored_prose_still_fail_closed": True,
    }


def install_comprehensive_human_evidence_report_v1() -> dict[str, Any]:
    state = {
        "status": "installed",
        "version": VERSION,
        **_install_renderer_projection(),
        **_install_spanish_literal_guard(),
        "verified_durable_human_evidence_only": True,
        "repository_inference_prohibited": True,
        "technical_scores_unchanged": True,
        "canonical_scope_ids_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return state


__all__ = [
    "VERSION",
    "build_report_package_with_human_context",
    "install_comprehensive_human_evidence_report_v1",
]
