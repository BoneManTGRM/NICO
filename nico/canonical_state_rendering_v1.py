from __future__ import annotations

from typing import Any

VERSION = "nico.canonical-state-rendering.v1"

CANONICAL_STATE_LABELS: dict[str, dict[str, str]] = {
    "supplied_verified": {
        "en": "Verified",
        "es-MX": "Verificado",
    },
    "supplied_unverified": {
        "en": "Supplied — independent verification pending",
        "es-MX": "Proporcionado — verificación independiente pendiente",
    },
    "not_supplied": {
        "en": "Not supplied",
        "es-MX": "No proporcionado",
    },
    "excluded_from_scope": {
        "en": "Excluded from scope",
        "es-MX": "Excluido del alcance",
    },
    "not_applicable": {
        "en": "Not applicable",
        "es-MX": "No aplica",
    },
    "framework_only": {
        "en": "Framework only — stakeholder validation pending",
        "es-MX": (
            "Solo marco de trabajo — pendiente de validación de las partes "
            "interesadas"
        ),
    },
    "review_required": {
        "en": "Human review required",
        "es-MX": "Revisión humana requerida",
    },
    "pending_human_approval": {
        "en": "Pending human approval",
        "es-MX": "Pendiente de aprobación humana",
    },
}


def canonical_locale(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("_", "-")
    return "es-MX" if normalized in {"es", "es-mx"} else "en"


def render_canonical_state(state: Any, locale: Any = "en") -> str:
    normalized = str(state or "").strip().casefold()
    if normalized not in CANONICAL_STATE_LABELS:
        raise ValueError(f"unsupported_canonical_state:{normalized or 'missing'}")
    return CANONICAL_STATE_LABELS[normalized][canonical_locale(locale)]


__all__ = [
    "CANONICAL_STATE_LABELS",
    "VERSION",
    "canonical_locale",
    "render_canonical_state",
]
