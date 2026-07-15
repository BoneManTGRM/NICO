from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_progress_observer_mounts_before_transport_bridge() -> None:
    layout = (ROOT / "apps/web/app/layout.tsx").read_text(encoding="utf-8")

    assert "import AssessmentLiveProgress" in layout
    assert layout.index("<AssessmentLiveProgress />") < layout.index("<AssessmentApiTransportBridge />")


def test_live_progress_observes_exact_run_status_and_uses_indeterminate_motion() -> None:
    source = (ROOT / "apps/web/app/AssessmentLiveProgress.tsx").read_text(encoding="utf-8")

    assert 'export const ASSESSMENT_PROGRESS_EVENT = "nico:assessment-progress"' in source
    assert "express-run|mid-run|full-run" in source
    assert "response.clone().json()" in source
    assert "Live backend assessment progress" in source
    assert "indeterminate" in source
    assert "Elapsed:" in source
    assert "status update" in source
    assert "pollAttempt / MAX_POLL_ATTEMPTS" not in source


def test_existing_fake_attempt_bar_is_hidden_when_live_progress_is_present() -> None:
    source = (ROOT / "apps/web/app/AssessmentLiveProgress.tsx").read_text(encoding="utf-8")

    assert '[aria-label="Automatic continuation in progress"] { display: none !important; }' in source
    assert "progress_percent" in source
    assert "completed / total" in source
