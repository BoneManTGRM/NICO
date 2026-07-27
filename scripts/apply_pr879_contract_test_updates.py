#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old!r}")
    target.write_text(source.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    replace_once(
        "tests/test_final_report_approval_semantics.py",
        '    assert "The NICO technical team must review and approve this exact evidence-bound edition before client delivery" in text\n',
        '    assert "An authorized NICO reviewer must approve this exact evidence-bound edition before it becomes client-ready" in text\n'
        '    assert "Open internal review" in text\n',
    )
    replace_once(
        "tests/test_simplified_review_retainer_workflows.py",
        '    assert "Final review, without the friction." in source\n',
        '    assert "Internal final review and client-ready authorization." in source\n',
    )
    replace_once(
        "tests/test_simplified_review_retainer_workflows.py",
        '    assert "ACEPTACIÓN CONTROLADA DE NICO" in source\n',
        '    assert "CONTROL INTERNO DE CALIDAD NICO" in source\n',
    )
    replace_once(
        "tests/test_two_service_review_terminal_phase_v12.py",
        '    expected = {\n        "Expert review required",\n        "Se requiere revisión experta",\n    }\n',
        '    expected = {\n        "Internal review required",\n        "Revisión interna requerida",\n    }\n',
    )
    replace_once(
        "scripts/two_service_live_acceptance_v3.py",
        'CURRENT_REVIEW_TERMINAL_PHASES = {\n    "Expert review required",\n    "Se requiere revisión experta",\n}\n',
        'CURRENT_REVIEW_TERMINAL_PHASES = {\n'
        '    "Internal review required",\n'
        '    "Revisión interna requerida",\n'
        '    # Historical aliases remain accepted for old deployed reports.\n'
        '    "Expert review required",\n'
        '    "Se requiere revisión experta",\n'
        '}\n',
    )
    replace_once(
        "scripts/two_service_live_acceptance_v3.py",
        "                review: findText(['Expert review', 'Human review', 'Revisión experta', 'Revisión humana']),\n",
        "                review: findText(['Internal review', 'Expert review', 'Human review', 'Revisión interna', 'Revisión experta', 'Revisión humana']),\n",
    )
    replace_once(
        "tests/test_unified_assessment_ui.py",
        '    assert "Technical analysis and report preparation are complete. The engagement is awaiting required human review." in source\n'
        '    assert "The NICO technical team must review and approve this exact evidence-bound edition before client delivery" in source\n',
        '    assert "Technical analysis and report preparation are complete. The engagement is awaiting internal technical review." in source\n'
        '    assert "An authorized NICO reviewer must approve this exact evidence-bound edition before it becomes client-ready" in source\n'
        '    assert "data-assessment-internal-review" in source\n',
    )
    replace_once(
        "tests/test_web_spanish_assessment_parity.py",
        '        "Se requiere revisión experta",\n        "Descargar PDF final",\n        "El análisis automatizado terminó.",\n        "debe revisar y aprobar esta edición exacta",\n',
        '        "Revisión interna requerida",\n        "Descargar PDF para revisión",\n        "El análisis automatizado terminó.",\n        "Un revisor autorizado de NICO debe aprobar esta edición exacta",\n',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
