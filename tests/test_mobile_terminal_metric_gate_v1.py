from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = (ROOT / "scripts/mobile_restart_live_acceptance_v3.py").read_text(encoding="utf-8")


def test_metrics_are_retained_before_supplemental_render_attempt() -> None:
    screenshot = PROOF.split("def screenshot(", 1)[1].split("class _SingleDispatchContext", 1)[0]
    capture = PROOF.split("def capture_terminal_metrics(", 1)[1].split("def goto(", 1)[0]

    assert "self.capture_terminal_metrics()" in screenshot
    assert "return self._page.screenshot" in screenshot
    assert screenshot.index("self.capture_terminal_metrics()") < screenshot.index("return self._page.screenshot")
    assert "self._terminal_metrics.update(metrics)" in capture
    assert "assert metrics.get" not in screenshot


def test_compact_gate_blocks_heavy_report_trees() -> None:
    validator = PROOF.split("def _validate_terminal_metrics", 1)[1].split("class _SingleDispatchPage", 1)[0]
    assert 'full_detail_count") or 0) == 0' in validator
    assert 'heavy_report_mounted_count") or 0) == 0' in validator
    assert 'stage_history_count") or 0) == 0' in validator
    assert 'scorecard_grid_count") or 0) == 0' in validator


def test_compact_gate_accounts_for_review_and_evidence_controls() -> None:
    validator = PROOF.split("def _validate_terminal_metrics", 1)[1].split("class _SingleDispatchPage", 1)[0]
    assert 'evidence_metric_count") or 0) <= 4' in validator
    assert 'internal_review_action_count") or 0) <= 1' in validator
    assert "MAX_COMPACT_NODE_COUNT = 1_500" in PROOF
    assert "MAX_COMPACT_SCROLL_HEIGHT = 7_000" in PROOF
    assert 'node_count") or 0) < MAX_COMPACT_NODE_COUNT' in validator
    assert 'scroll_height") or 0) < MAX_COMPACT_SCROLL_HEIGHT' in validator


def test_metrics_are_enforced_after_the_base_proof_returns() -> None:
    run_proof = PROOF.split("def run_proof(", 1)[1].split("def main(", 1)[0]
    assert "result = _ORIGINAL_RUN_PROOF(wrapped, args)" in run_proof
    assert "_validate_terminal_metrics(wrapped.terminal_metrics)" in run_proof
    assert run_proof.index("result = _ORIGINAL_RUN_PROOF") < run_proof.index("_validate_terminal_metrics")
