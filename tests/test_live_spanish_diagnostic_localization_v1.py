from pathlib import Path

SOURCE = Path(
    "apps/web/app/assessment/AssessmentDynamicSpanishLocalization.tsx"
).read_text(encoding="utf-8")


def test_live_spanish_boundary_uses_full_localizer_for_dynamic_copy() -> None:
    assert 'import {localizeSpanishText} from "./AssessmentSpanishLocalization";' in SOURCE
    assert "export function localizeLiveSpanishText" in SOURCE
    assert "return localizeSpanishText(localized);" in SOURCE
    assert "MutationObserver" in SOURCE
    assert "translateTextNode(record.target);" in SOURCE
    assert "for (const node of record.addedNodes) translateTree(node);" in SOURCE


def test_known_spanish_publication_diagnostic_is_localized() -> None:
    assert "Spanish Comprehensive report retained NICO-authored English presentation copy:" in SOURCE
    assert "El informe Integral en español conservó texto de presentación en inglés generado por NICO:" in SOURCE
    assert "Review-Required Candidate Register" in SOURCE
    assert "Registro de candidatos que requieren revisión" in SOURCE
    assert "Material confirmado findings" in SOURCE
    assert "Hallazgos materiales confirmados" in SOURCE
    assert "verificada material findings" in SOURCE
    assert "hallazgos materiales verificados" in SOURCE
    assert "Strengthen architecture boundaries" in SOURCE
    assert "Reforzar los límites de arquitectura" in SOURCE
    assert "Sustainable delivery capacity is derived" in SOURCE
    assert "La capacidad de entrega sostenible" in SOURCE
    assert "Exact-commit executable source signals were analyzed" in SOURCE
    assert "Se analizaron las señales ejecutables del código fuente del commit exacto" in SOURCE


def test_machine_identifiers_stay_exact_except_known_display_diagnostic() -> None:
    assert 'value.includes("v2_production_publication_failed")' in SOURCE
    assert 'const inCode = Boolean(parent.closest("code"));' in SOURCE
    assert 'parent.closest("pre") || (inCode && !knownDiagnosticCode(source))' in SOURCE
    assert "canonical diagnostics remain untouched" in SOURCE
