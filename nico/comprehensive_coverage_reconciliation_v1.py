"""Bounded report-only coverage definitions; retained source records are not edited."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re
from typing import Any, Mapping

VERSION = "nico.report-coverage-reconciliation.v1"
ACQUISITION_NOTE = (
    "Required source evidence was acquired from credential-free exact-SHA Git to "
    "preserve the anonymous public access binding without depending on GitHub API object-read quota."
)
ARCHITECTURE_DEFINITION = (
    "GitHub snapshot footprint: lowercase .py/.ts/.tsx/.js/.jsx suffixes; exclude root tests/ "
    "paths and any filename containing test (case-insensitive). This is not complexity eligibility."
)
PROVIDER_ARCHITECTURE_DEFINITION = (
    "Provider snapshot footprint: lowercase .py/.ts/.tsx/.js/.jsx/.cs/.java/.go/.rs suffixes; "
    "exclude paths containing /test or starting with test (case-insensitive)."
)
COMPLEXITY_DEFINITION = (
    "Case-insensitive .py/.js/.jsx/.ts/.tsx paths; exclude /test/, /tests/, test_, _test., "
    ".test., .spec., dependency/build/vendor paths and .min.js. Each path is counted once."
)
AVAILABILITY_DEFINITION = (
    "Collection-note entries are messages, not files. Unavailable files count distinct retained "
    "unavailable_paths. Zero recorded unavailable paths does not prove all repository files were read."
)
POPULATION_NOTE = "Architecture footprint and complexity eligibility use different filters; neither count is an exhaustive assessment."
UNKNOWN_ARCHITECTURE = "The architecture population definition is not established by retained provider metadata."
_PROFILE_WARNING = re.compile(r"^(\d+) captured-commit profile item\(s\) were unavailable; complexity coverage is limited to readable sampled files\.$")
_ARCH_COUNT = re.compile(r"^(?:Source files|Architecture footprint source files): (\d+)\.$")

# NICO-authored labels only. Source paths and the retained note itself are not rewritten.
COPY_ES = {
    "Coverage population and availability reconciliation": "Conciliación de poblaciones y disponibilidad de cobertura",
    "Architecture footprint filter": "Filtro de archivos de arquitectura",
    "Complexity eligibility filter": "Filtro de elegibilidad para complejidad",
    "Population distinction": "Distinción de poblaciones",
    "Profile collection note entries": "Entradas de notas de recopilación del perfil",
    "Unavailable file paths recorded": "Rutas de archivos no disponibles registradas",
    "Availability interpretation": "Interpretación de disponibilidad",
    "Recorded acquisition note (informational)": "Nota de adquisición registrada (informativa)",
    "Assessed source revision": "Revisión del código evaluado",
    "Reconciliation limitation": "Limitación de la conciliación",
    "Recorded unavailable-file count": "Conteo registrado de archivos no disponibles",
    "Availability count correction": "Corrección del conteo de disponibilidad",
    "The displayed unavailable-file count is derived from distinct retained paths; the original count is preserved in canonical evidence.": "El conteo mostrado de archivos no disponibles se deriva de las rutas distintas conservadas; el conteo original permanece en la evidencia canónica.",
    "Profile availability records disagree; availability is not reconciled.": "Los registros de disponibilidad del perfil discrepan; la disponibilidad no está conciliada.",
    ARCHITECTURE_DEFINITION: "Archivos del repositorio GitHub: sufijos en minúsculas .py/.ts/.tsx/.js/.jsx; se excluyen rutas raíz tests/ y nombres que contengan test, sin distinguir mayúsculas. No equivale a elegibilidad para complejidad.",
    PROVIDER_ARCHITECTURE_DEFINITION: "Archivos del proveedor: sufijos en minúsculas .py/.ts/.tsx/.js/.jsx/.cs/.java/.go/.rs; se excluyen rutas que contengan /test o empiecen con test, sin distinguir mayúsculas.",
    COMPLEXITY_DEFINITION: "Rutas .py/.js/.jsx/.ts/.tsx sin distinguir mayúsculas; se excluyen /test/, /tests/, test_, _test., .test., .spec., rutas de dependencias/compilación/vendor y .min.js. Cada ruta se cuenta una vez.",
    AVAILABILITY_DEFINITION: "Las notas de recopilación son mensajes, no archivos. Los archivos no disponibles cuentan rutas distintas de unavailable_paths. Cero rutas registradas no demuestra que se leyeran todos los archivos del repositorio.",
    POPULATION_NOTE: "Los archivos de arquitectura y los elegibles para complejidad usan filtros distintos; ningún conteo representa una evaluación exhaustiva.",
    UNKNOWN_ARCHITECTURE: "Los metadatos conservados del proveedor no establecen la definición de la población de arquitectura.",
    ACQUISITION_NOTE: "La evidencia de código requerida se obtuvo mediante Git del SHA exacto sin credenciales para conservar el vínculo de acceso público anónimo sin depender de la cuota de lectura de objetos de la API de GitHub.",
}


def _messages(profile: Mapping[str, Any]) -> list[str] | None:
    value = profile.get("unavailable_item_notes")
    return list(value) if isinstance(value, list) and all(isinstance(v, str) for v in value) else None


def _unavailable_paths(profile: Mapping[str, Any]) -> list[str] | None:
    value = profile.get("unavailable_paths")
    return sorted(set(value)) if isinstance(value, list) and all(isinstance(v, str) and v for v in value) else None


def _provider(stages: list[dict[str, Any]]) -> str:
    values = set()
    for stage in stages:
        if stage.get("stage_id") == "repository_and_delivery_evidence":
            for line in stage.get("evidence") or []:
                match = re.fullmatch(r"(?:Provider|Proveedor): (.+)\.", str(line))
                if match:
                    values.add(match[1].casefold())
    return next(iter(values)) if len(values) == 1 else ""


def reconcile_report_coverage(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Project retained profile units before hashing a new unapproved edition.

    Do not normalize raw profile_coverage, observations, scanner records or scores.
    Inconsistent profile records do not authorize removing a historical warning.
    Approval is never carried onto changed content by this helper.
    """
    result = deepcopy(dict(canonical))
    if (result.get("client_delivery_allowed") is True or result.get("human_review_completed") is True
            or result.get("report_finality") in {"approved_final", "operator_approved", "operator_approved_final"}):
        return result
    stages = result.get("stage_summaries")
    if not isinstance(stages, list):
        return result
    profiles = [s["profile_coverage"] for s in stages if isinstance(s, dict)
                and isinstance(s.get("profile_coverage"), dict) and s["profile_coverage"]]
    if not profiles or any(p.get("version") != "nico.repository_profile_coverage.v1" for p in profiles):
        return result
    provider = _provider(stages)
    definition = (ARCHITECTURE_DEFINITION if provider == "github" else
                  PROVIDER_ARCHITECTURE_DEFINITION if provider in {"gitlab", "bitbucket cloud", "azure devops", "bitbucket_cloud", "azure_devops"}
                  else UNKNOWN_ARCHITECTURE)
    # The two retained stage copies must agree before a shared note is reclassified.
    availability = [(_messages(p), _unavailable_paths(p)) for p in profiles]
    def signature(value: tuple[list[str] | None, list[str] | None]) -> tuple[Any, Any]:
        notes, paths = value
        return (Counter(notes) if notes is not None else None, paths)
    consistent = all(signature(value) == signature(availability[0]) for value in availability)
    notes, paths = availability[0]
    informational = consistent and provider == "github" and notes is not None and ACQUISITION_NOTE in notes
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        profile = stage.get("profile_coverage")
        if isinstance(profile, dict) and profile:
            local_notes, local_paths = _messages(profile), _unavailable_paths(profile)
            stage["coverage_reconciliation"] = {
                "version": VERSION,
                "assessed_commit": (result.get("identity") or {}).get("commit_sha"),
                "architecture_definition": definition,
                "complexity_definition": COMPLEXITY_DEFINITION,
                "profile_note_entry_count": len(local_notes) if local_notes is not None else None,
                "unavailable_file_path_count": len(local_paths) if local_paths is not None else None,
                "retained_unavailable_file_count": profile.get("unavailable_profile_files"),
                "source": "retained profile_coverage.unavailable_item_notes and unavailable_paths",
                "profile_records_agree": consistent,
                "informational_acquisition_note": ACQUISITION_NOTE if informational else None,
            }
        if not consistent or notes is None:
            continue
        original_limits = stage.get("unavailable")
        if (informational and stage.get("stage_id") == "repository_and_delivery_evidence"
                and isinstance(original_limits, list) and ACQUISITION_NOTE in original_limits):
            acquisition_count = original_limits.count(ACQUISITION_NOTE)
            stage["evidence"] = [
                (f"Collection notes recorded: {match[1]}; informational acquisition notes: {acquisition_count}; "
                 f"remaining limitation notes: {len(original_limits) - acquisition_count}.")
                if ((match := re.fullmatch(r"Collection limitations recorded: (\d+)\.", str(line)))
                    and int(match[1]) == len(original_limits)) else line
                for line in stage.get("evidence") or []
            ]
        for field in ("unavailable", "unavailable_data_notes"):
            values = stage.get(field)
            if not isinstance(values, list):
                continue
            kept = []
            for line in values:
                match = _PROFILE_WARNING.fullmatch(str(line))
                # Only the demonstrated all-informational population can remove the
                # false unavailable-item warning. Unknown or genuine failure notes stay.
                if (match and int(match[1]) == len(notes) and notes
                        and informational and all(n == ACQUISITION_NOTE for n in notes)
                        and paths == []):
                    continue
                if informational and line == ACQUISITION_NOTE:
                    continue  # Retained literally in profile and explicitly in the table.
                kept.append(line)
            stage[field] = kept
    assessment = result.get("assessment")
    if isinstance(assessment, dict):
        # Relabel the retained measure, not its value or existing scoring policy.
        for section in assessment.get("sections") or []:
            if isinstance(section, dict) and section.get("id") == "architecture_debt" and provider:
                section["evidence"] = [
                    f"Architecture footprint source files: {match[1]}." if (match := _ARCH_COUNT.fullmatch(str(line))) else line
                    for line in section.get("evidence") or []
                ]
                if POPULATION_NOTE not in section["evidence"]:
                    section["evidence"].append(POPULATION_NOTE)
        if informational and isinstance(assessment.get("unavailable_data_notes"), list):
            old = assessment["unavailable_data_notes"]
            updated = [line for line in old if line != ACQUISITION_NOTE]
            assessment["unavailable_data_notes"] = updated
            if assessment.get("unavailable_note_count") == len(old):
                assessment["unavailable_note_count"] = len(updated)
        if isinstance(assessment.get("stage_summaries"), list):
            assessment["stage_summaries"] = deepcopy(stages)
    return result


def coverage_reconciliation_table(stage: Mapping[str, Any]) -> dict[str, Any] | None:
    """A compact common table for PDF, Markdown/HTML and canonical-derived views."""
    record = stage.get("coverage_reconciliation")
    if not stage.get("profile_coverage") or not isinstance(record, Mapping) or record.get("version") != VERSION:
        return None
    rows = [
        ["Architecture footprint filter", record["architecture_definition"]],
        ["Complexity eligibility filter", record["complexity_definition"]],
        ["Population distinction", POPULATION_NOTE],
        ["Profile collection note entries", record["profile_note_entry_count"]],
        ["Unavailable file paths recorded", record["unavailable_file_path_count"]],
        ["Availability interpretation", AVAILABILITY_DEFINITION],
        ["Assessed source revision", record.get("assessed_commit")],
    ]
    original_count = record.get("retained_unavailable_file_count")
    if original_count is not None and original_count != record["unavailable_file_path_count"]:
        rows.extend([
            ["Recorded unavailable-file count", original_count],
            ["Availability count correction", "The displayed unavailable-file count is derived from distinct retained paths; the original count is preserved in canonical evidence."],
        ])
    if record.get("profile_records_agree") is not True:
        rows.append(["Reconciliation limitation", "Profile availability records disagree; availability is not reconciled."])
    if record.get("informational_acquisition_note"):
        rows.append(["Recorded acquisition note (informational)", record["informational_acquisition_note"]])
    return {"title": "Coverage population and availability reconciliation", "columns": ["Measure", "Value"], "rows": rows}
