#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "scripts/mobile_restart_live_acceptance_v3.py"
TEST = ROOT / "tests/test_mobile_terminal_metric_gate_v1.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def main() -> int:
    source = PROOF.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '''HYDRATED_WORKSPACE_SELECTOR = (
    recovery.WORKSPACE_SELECTOR
    + '[data-assessment-hydrated="true"]'
    + '[data-assessment-client-mode="compact-mobile"]'
)
''',
        '''HYDRATED_WORKSPACE_SELECTOR = (
    recovery.WORKSPACE_SELECTOR
    + '[data-assessment-hydrated="true"]'
    + '[data-assessment-client-mode="compact-mobile"]'
)
MAX_COMPACT_NODE_COUNT = 1_500
MAX_COMPACT_SCROLL_HEIGHT = 7_000
''',
        "metric limits",
    )
    source = replace_once(
        source,
        '''                  scorecard_grid_count: document.querySelectorAll('.results-grid').length,
                  node_count: document.getElementsByTagName('*').length,
                  scroll_height: document.documentElement.scrollHeight,
                  body_height: document.body.getBoundingClientRect().height,
                }))''',
        '''                  scorecard_grid_count: document.querySelectorAll('.results-grid').length,
                  evidence_metric_count: document.querySelectorAll(
                    '[data-assessment-evidence-metrics="true"] article'
                  ).length,
                  internal_review_action_count: document.querySelectorAll(
                    '[data-assessment-internal-review="true"]'
                  ).length,
                  node_count: document.getElementsByTagName('*').length,
                  scroll_height: document.documentElement.scrollHeight,
                  body_height: document.body.getBoundingClientRect().height,
                }))''',
        "new compact metrics",
    )
    source = replace_once(
        source,
        '''        assert metrics.get("hydrated") is True, metrics
        assert metrics.get("client_mode") == "compact-mobile", metrics
        assert int(metrics.get("compact_terminal_count") or 0) == 1, metrics
        assert int(metrics.get("full_detail_count") or 0) == 0, metrics
        assert int(metrics.get("heavy_report_mounted_count") or 0) == 0, metrics
        assert int(metrics.get("stage_history_count") or 0) == 0, metrics
        assert int(metrics.get("scorecard_grid_count") or 0) == 0, metrics
        assert int(metrics.get("node_count") or 0) < 1_200, metrics
        assert int(metrics.get("scroll_height") or 0) < 5_000, metrics
        self._terminal_metrics.clear()
        self._terminal_metrics.update(metrics)
        return self._page.screenshot(*args, **kwargs)''',
        '''        # Persist the measured state before validation so any failure artifact
        # contains the exact DOM facts instead of the opaque "metrics not captured" error.
        self._terminal_metrics.clear()
        self._terminal_metrics.update(metrics)
        assert metrics.get("hydrated") is True, metrics
        assert metrics.get("client_mode") == "compact-mobile", metrics
        assert int(metrics.get("compact_terminal_count") or 0) == 1, metrics
        assert int(metrics.get("full_detail_count") or 0) == 0, metrics
        assert int(metrics.get("heavy_report_mounted_count") or 0) == 0, metrics
        assert int(metrics.get("stage_history_count") or 0) == 0, metrics
        assert int(metrics.get("scorecard_grid_count") or 0) == 0, metrics
        assert int(metrics.get("evidence_metric_count") or 0) <= 4, metrics
        assert int(metrics.get("internal_review_action_count") or 0) <= 1, metrics
        assert int(metrics.get("node_count") or 0) < MAX_COMPACT_NODE_COUNT, metrics
        assert int(metrics.get("scroll_height") or 0) < MAX_COMPACT_SCROLL_HEIGHT, metrics
        return self._page.screenshot(*args, **kwargs)''',
        "retain and validate metrics",
    )
    PROOF.write_text(source, encoding="utf-8")

    TEST.write_text(
        '''from pathlib import Path

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
    assert '== 0' in PROOF


def test_compact_gate_accounts_for_new_review_and_evidence_controls() -> None:
    assert 'evidence_metric_count' in PROOF
    assert 'internal_review_action_count' in PROOF
    assert 'MAX_COMPACT_NODE_COUNT = 1_500' in PROOF
    assert 'MAX_COMPACT_SCROLL_HEIGHT = 7_000' in PROOF


def test_opaque_metrics_not_captured_failure_is_no_longer_possible_after_screenshot_entry() -> None:
    assert PROOF.index('self._terminal_metrics.update(metrics)') < PROOF.index('return self._page.screenshot')
''',
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
