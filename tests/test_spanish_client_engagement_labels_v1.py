from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "apps" / "web" / "app" / "assessment" / "StrategicEvidenceForm.tsx"
).read_text(encoding="utf-8")
STYLES = (
    ROOT / "apps" / "web" / "app" / "assessment" / "strategicEvidence.module.css"
).read_text(encoding="utf-8")
DEFINITIONS_SOURCE = (
    ROOT / "apps" / "web" / "app" / "assessment" / "strategicEvidence.ts"
).read_text(encoding="utf-8")

EXPECTED_FIELD_LABELS = {
    "test_cases": ("Test cases", "Casos de prueba"),
    "observed_results": ("Observed results", "Resultados observados"),
    "matrix": ("Coverage matrix", "Matriz de cobertura"),
    "observations": ("Observations", "Observaciones"),
    "objectives": ("Objectives", "Objetivos"),
    "constraints": ("Constraints", "Restricciones"),
    "access_method": ("Access Method", "Método de acceso"),
    "primary_technical_contact": (
        "Primary Technical Contact",
        "Contacto técnico principal",
    ),
    "authorized_scope": ("Authorized Scope", "Alcance autorizado"),
    "incidents": ("Incidents", "Incidentes"),
    "success_measures": ("Success measures", "Medidas de éxito"),
    "requirements": ("Requirements", "Requisitos"),
    "authority_status": (
        "Source authority status",
        "Estado de autoridad de la fuente",
    ),
    "decisions": ("Decisions", "Decisiones"),
}


def _authored_field_labels(locale: str) -> dict[str, str]:
    labels = SOURCE.split("const EVIDENCE_FIELD_LABELS = {", 1)[1].split(
        "} satisfies Record<Locale, Record<string, string>>;", 1
    )[0]
    if locale == "en":
        body = labels.split("  en: {", 1)[1].split('\n  },\n  "es-MX": {', 1)[0]
    else:
        body = labels.split('  "es-MX": {', 1)[1].rsplit("\n  },", 1)[0]
    return dict(re.findall(r'^    ([a-z_]+): "([^"]+)",$', body, re.MULTILINE))


def _authoritative_evidence_fields() -> set[str]:
    definitions = DEFINITIONS_SOURCE.split(
        "export const STRATEGIC_EVIDENCE_DEFINITIONS", 1
    )[1].split("]\n\nexport function evidenceFields", 1)[0]
    field_arrays = re.findall(
        r'(?:requiredFields|fields): \[([^\]]*)\]', definitions
    )
    return {
        field
        for field_array in field_arrays
        for field in re.findall(r'"([a-z_]+)"', field_array)
    }


def test_mobile_client_engagement_labels_are_bilingual() -> None:
    assert _authored_field_labels("en") == {
        key: english for key, (english, _) in EXPECTED_FIELD_LABELS.items()
    }
    assert _authored_field_labels("es-MX") == {
        key: spanish for key, (_, spanish) in EXPECTED_FIELD_LABELS.items()
    }
    assert '<span>{copy.field(field)}</span>' in SOURCE
    assert 'field: (name: string) => evidenceFieldLabel(name, "en")' in SOURCE
    assert 'field: (name: string) => evidenceFieldLabel(name, "es-MX")' in SOURCE


def test_client_engagement_transport_keys_remain_stable() -> None:
    assert (
        'const MOBILE_CLIENT_ENGAGEMENT_FIELDS = ["access_method", '
        '"primary_technical_contact", "authorized_scope"] as const;'
    ) in SOURCE
    assert "setEvidenceField(" in SOURCE
    assert '"stakeholder_context"' in SOURCE
    assert "field," in SOURCE
    assert 'engagement.evidence[field]' in SOURCE


def test_known_evidence_fields_are_localized_without_machine_key_fallback() -> None:
    assert set(EXPECTED_FIELD_LABELS) == _authoritative_evidence_fields()
    assert set(_authored_field_labels("en")) == _authoritative_evidence_fields()
    assert set(_authored_field_labels("es-MX")) == _authoritative_evidence_fields()
    assert 'name.replaceAll("_", " ")' not in SOURCE
    assert 'EVIDENCE_FIELD_LABELS[locale][name]' in SOURCE
    assert '"Additional evidence"' in SOURCE
    assert '"Evidencia adicional"' in SOURCE


def test_evidence_field_labels_preserve_authored_spanish_casing() -> None:
    assert ".evidenceTextareaLabel {\n  text-transform: none;\n}" in STYLES
    assert ".evidenceTextareaLabel {\n  text-transform: capitalize;\n}" not in STYLES
