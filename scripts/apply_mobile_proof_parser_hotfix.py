#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "scripts/mobile_restart_live_acceptance_v1.py"
TEST = ROOT / "tests/test_mobile_restart_compact_state_parser_v1.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return source.replace(old, new, 1)


def main() -> int:
    source = PROOF.read_text(encoding="utf-8")
    source = replace_once(
        source,
        'TERMINAL_PHASES = {"Expert review required", "Se requiere revisión experta"}',
        '''TERMINAL_PHASES = {
    "Internal review required",
    "Revisión interna requerida",
    # Historical labels remain accepted for exact-run compatibility with older deployments.
    "Expert review required",
    "Se requiere revisión experta",
}''',
        "terminal phase vocabulary",
    )
    source = replace_once(
        source,
        '''          const articles = Array.from(section.querySelectorAll('article'));
          const find = labels => {
            const article = articles.find(item => labels.includes(compact(item.querySelector('b')?.textContent)));
            const code = article?.querySelector('code');
            return compact(code?.getAttribute('title') || code?.textContent || article?.querySelector('span')?.textContent);
          };''',
        '''          // The compact iPhone result tree stores technical identity inside
          // <details><p> rows while desktop scorecards use <article> rows.
          const rows = Array.from(section.querySelectorAll('article, details p'));
          const find = labels => {
            const row = rows.find(item => labels.includes(compact(item.querySelector('b')?.textContent)));
            const code = row?.querySelector('code');
            return compact(code?.getAttribute('title') || code?.textContent || row?.querySelector('span')?.textContent);
          };
          const headerRunId = compact(section.querySelector('.section-head h2')?.getAttribute('title'));''',
        "compact identity reader",
    )
    source = replace_once(
        source,
        "            run_id: find(['Run ID', 'ID de ejecución']),",
        "            run_id: find(['Run ID', 'ID de ejecución']) || headerRunId,",
        "run identity fallback",
    )
    source = replace_once(
        source,
        "            review: find(['Expert review', 'Human review', 'Revisión experta', 'Revisión humana']),",
        "            review: find(['Internal review', 'Expert review', 'Human review', 'Revisión interna', 'Revisión experta', 'Revisión humana']),",
        "internal review reader",
    )
    PROOF.write_text(source, encoding="utf-8")

    TEST.write_text(
        '''from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")


def test_mobile_proof_reads_compact_identity_rows() -> None:
    assert "querySelectorAll('article, details p')" in PROOF
    assert "const headerRunId" in PROOF
    assert "|| headerRunId" in PROOF


def test_mobile_proof_accepts_current_internal_review_vocabulary() -> None:
    assert '"Internal review required"' in PROOF
    assert '"Revisión interna requerida"' in PROOF
    assert "'Internal review'" in PROOF
    assert "'Revisión interna'" in PROOF


def test_mobile_proof_keeps_legacy_terminal_compatibility() -> None:
    assert '"Expert review required"' in PROOF
    assert '"Se requiere revisión experta"' in PROOF
''',
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
