from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "apps" / "web" / "app" / "assessment" / "StrategicEvidenceForm.tsx"
).read_text(encoding="utf-8")
STYLES = (
    ROOT / "apps" / "web" / "app" / "assessment" / "strategicEvidence.module.css"
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


def test_mobile_client_engagement_labels_are_bilingual() -> None:
    for english, spanish in EXPECTED_FIELD_LABELS.values():
        assert f'"{english}"' in SOURCE
        assert f'"{spanish}"' in SOURCE
    assert '<span>{copy.field(field)}</span>' in SOURCE


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
    for key in EXPECTED_FIELD_LABELS:
        assert f'{key}: "' in SOURCE
    assert 'name.replaceAll("_", " ")' not in SOURCE
    assert 'EVIDENCE_FIELD_LABELS[locale][name]' in SOURCE
    assert '"Additional evidence"' in SOURCE
    assert '"Evidencia adicional"' in SOURCE


def test_evidence_field_labels_preserve_authored_spanish_casing() -> None:
    assert ".evidenceTextareaLabel {\n  text-transform: none;\n}" in STYLES
    assert ".evidenceTextareaLabel {\n  text-transform: capitalize;\n}" not in STYLES
