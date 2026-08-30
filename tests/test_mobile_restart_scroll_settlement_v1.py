from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROOF = (
    ROOT / "scripts" / "mobile_restart_live_acceptance_v1.py"
).read_text(encoding="utf-8")


def test_terminal_scroll_round_trip_waits_for_each_smooth_scroll_to_settle() -> None:
    helper = PROOF.split("def _exercise_scroll_round_trip", 1)[1].split(
        "def _observe_terminal_stability", 1
    )[0]
    assert "document.scrollingElement || document.documentElement" in helper
    assert "Math.abs(window.scrollY - maxY) <= 2" in helper
    assert "Math.abs(window.scrollY) <= 1" in helper
    assert helper.count("page.wait_for_function(") == 2
    assert helper.index("Math.abs(window.scrollY - maxY) <= 2") < helper.index(
        "Math.abs(window.scrollY) <= 1"
    )


def test_terminal_observation_uses_the_settled_scroll_round_trip() -> None:
    observation = PROOF.split("def _observe_terminal_stability", 1)[1].split(
        "def _record_native_visibility_transition", 1
    )[0]
    assert "scroll = _exercise_scroll_round_trip(page)" in observation
    assert "window.scrollTo(0, document.documentElement.scrollHeight)" not in observation
