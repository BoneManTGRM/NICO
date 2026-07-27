from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")


def test_metrics_are_retained_before_assertions() -> None:
    stored = PROOF.index('self._terminal_metrics.update(metrics)')
    hydrated = PROOF.index('assert metrics.get("hydrated") is True')
    assert stored < hydrated


def test_compact_gate_blocks_heavy_report_trees() -> None:
    assert 'full_detail_count' in PROOF
    assert 'heavy_report_mounted_count' in PROOF
    assert 'stage_history_count' in PROOF
    assert 'scorecard_grid_count' in PROOF


def test_compact_gate_accounts_for_review_and_evidence_controls() -> None:
    assert 'evidence_metric_count' in PROOF
    assert 'internal_review_action_count' in PROOF
    assert 'MAX_COMPACT_NODE_COUNT = 1_500' in PROOF
    assert 'MAX_COMPACT_SCROLL_HEIGHT = 7_000' in PROOF


def test_screenshot_records_metrics_before_render_attempt() -> None:
    assert PROOF.index('self._terminal_metrics.update(metrics)') < PROOF.index('return self._page.screenshot')
