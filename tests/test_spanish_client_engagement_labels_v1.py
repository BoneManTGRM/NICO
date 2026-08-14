from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "apps" / "web" / "app" / "assessment" / "StrategicEvidenceForm.tsx"
).read_text(encoding="utf-8")


def test_mobile_client_engagement_labels_are_bilingual() -> None:
    assert '"Método de acceso"' in SOURCE
    assert '"Contacto técnico principal"' in SOURCE
    assert '"Alcance autorizado"' in SOURCE
    assert '"Access Method"' in SOURCE
    assert '"Primary Technical Contact"' in SOURCE
    assert '"Authorized Scope"' in SOURCE
    assert '<span>{copy.field(field)}</span>' in SOURCE


def test_client_engagement_transport_keys_remain_stable() -> None:
    assert (
        'const CLIENT_ENGAGEMENT_FIELDS = ["access_method", '
        '"primary_technical_contact", "authorized_scope"] as const;'
    ) in SOURCE
    assert 'setEvidenceField("stakeholder_context", field,' in SOURCE
    assert 'engagement.evidence[field]' in SOURCE


def test_unrelated_evidence_fields_keep_existing_fallback_labels() -> None:
    assert SOURCE.count('name.replaceAll("_", " ")') == 2
    assert SOURCE.count('name === "access_method"') == 2
    assert SOURCE.count('name === "primary_technical_contact"') == 2
    assert SOURCE.count('name === "authorized_scope"') == 2
