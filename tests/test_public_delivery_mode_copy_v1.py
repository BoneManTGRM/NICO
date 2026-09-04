from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_runtime_targets_node_24() -> None:
    package = (ROOT / "apps/web/package.json").read_text()
    assert '"node": "24.x"' in package
    assert '"node": "20.x"' not in package


def test_public_copy_distinguishes_human_and_automated_authorization() -> None:
    layout = (ROOT / "apps/web/app/layout.tsx").read_text()
    assessment = (ROOT / "apps/web/app/assessment/assessmentCopy.ts").read_text()
    services = (ROOT / "apps/web/app/services/page.tsx").read_text()

    assert "Expert-led" not in layout
    assert "Every client-facing recommendation is internally reviewed before release." not in assessment
    assert "Human-reviewed Comprehensive" in assessment
    assert "Authorized Automated Technical Assessment" in assessment
    assert "Human-reviewed Comprehensive" in services
    assert "Authorized Automated Technical Assessment" in services
    assert "No human specialist review" in services
    assert "review queue is empty" in services
