#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "scripts/mobile_restart_live_acceptance_v1.py"
MOBILE_WORKFLOW = ROOT / ".github/workflows/mobile-restart-production-proof.yml"
IOS_WORKFLOW = ROOT / ".github/workflows/ios-webkit-paint-proof.yml"
TEST = ROOT / "tests/test_mobile_restart_compact_identity_contract_v1.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def patch_proof() -> None:
    source = PROOF.read_text(encoding="utf-8")
    source = replace_once(
        source,
        'TERMINAL_PHASES = {"Expert review required", "Se requiere revisión experta"}',
        '''TERMINAL_PHASES = {
    "Internal review required",
    "Revisión interna requerida",
    # Historical aliases remain accepted for already-deployed editions.
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
        '''          // Desktop identity cards use <article>; the compact iPhone tree uses
          // lightweight <details><p> rows. Both are real rendered identity surfaces.
          const identityRows = Array.from(section.querySelectorAll('article, details p'));
          const find = labels => {
            const row = identityRows.find(item => labels.includes(compact(item.querySelector('b')?.textContent)));
            const code = row?.querySelector('code');
            return compact(code?.getAttribute('title') || code?.textContent || row?.querySelector('span')?.textContent);
          };''',
        "compact identity selector",
    )
    source = replace_once(
        source,
        '''            review: find(['Expert review', 'Human review', 'Revisión experta', 'Revisión humana']),''',
        '''            review: find(['Internal review', 'Expert review', 'Human review', 'Revisión interna', 'Revisión experta', 'Revisión humana']),''',
        "internal review selector",
    )
    PROOF.write_text(source, encoding="utf-8")


def patch_mobile_workflow() -> None:
    source = MOBILE_WORKFLOW.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '''          proof = Path("scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")
          assert 'nico.mobile_restart_live_acceptance.single_dispatch.v3' in proof''',
        '''          proof = Path("scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")
          base = Path("scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")
          assert 'nico.mobile_restart_live_acceptance.single_dispatch.v3' in proof
          assert "querySelectorAll('article, details p')" in base
          assert '"Internal review required"' in base
          assert '"Revisión interna requerida"' in base
          assert "'Internal review', 'Expert review'" in base''',
        "mobile contract assertions",
    )
    MOBILE_WORKFLOW.write_text(source, encoding="utf-8")


def patch_ios_workflow() -> None:
    source = IOS_WORKFLOW.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '''          proof = Path("scripts/mobile_restart_live_acceptance_v2.py").read_text(encoding="utf-8")
          dispatch = Path("scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")''',
        '''          proof = Path("scripts/mobile_restart_live_acceptance_v2.py").read_text(encoding="utf-8")
          base = Path("scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")
          dispatch = Path("scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")''',
        "ios base proof load",
    )
    source = replace_once(
        source,
        '''          assert 'nico.mobile_restart_live_acceptance.webkit.v3' in proof
          assert 'data-mobile-evidence-boundary="true"' in proof''',
        '''          assert 'nico.mobile_restart_live_acceptance.webkit.v3' in proof
          assert "querySelectorAll('article, details p')" in base
          assert '"Internal review required"' in base
          assert '"Revisión interna requerida"' in base
          assert "'Internal review', 'Expert review'" in base
          assert 'data-mobile-evidence-boundary="true"' in proof''',
        "ios compact identity assertions",
    )
    IOS_WORKFLOW.write_text(source, encoding="utf-8")


def write_test() -> None:
    TEST.write_text(
        '''from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")
MOBILE_WORKFLOW = (ROOT / ".github/workflows/mobile-restart-production-proof.yml").read_text(encoding="utf-8")
IOS_WORKFLOW = (ROOT / ".github/workflows/ios-webkit-paint-proof.yml").read_text(encoding="utf-8")


def test_mobile_proof_reads_the_actual_compact_identity_dom() -> None:
    assert "querySelectorAll('article, details p')" in PROOF
    assert "const identityRows" in PROOF
    assert "const row = identityRows.find" in PROOF
    assert "row?.querySelector('code')" in PROOF


def test_mobile_proof_accepts_current_internal_review_vocabulary() -> None:
    assert '"Internal review required"' in PROOF
    assert '"Revisión interna requerida"' in PROOF
    assert "'Internal review', 'Expert review'" in PROOF
    assert "'Revisión interna', 'Revisión experta'" in PROOF


def test_both_release_contracts_pin_the_compact_identity_selector() -> None:
    for workflow in (MOBILE_WORKFLOW, IOS_WORKFLOW):
        assert "querySelectorAll('article, details p')" in workflow
        assert '"Internal review required"' in workflow
        assert '"Revisión interna requerida"' in workflow


def test_proof_does_not_fall_back_to_url_identity_as_ui_evidence() -> None:
    wait_body = PROOF.split("def _wait_for_same_run_ui", 1)[1].split("def _wait_for_terminal", 1)[0]
    assert 'last.get("run_id") == run_id' in wait_body
    assert 'page_url' not in wait_body
''',
        encoding="utf-8",
    )


def main() -> int:
    patch_proof()
    patch_mobile_workflow()
    patch_ios_workflow()
    write_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
