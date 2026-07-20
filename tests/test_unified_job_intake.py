from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START_JOB = ROOT / "apps" / "web" / "app" / "start-job" / "page.tsx"
EASY = ROOT / "apps" / "web" / "app" / "easy" / "page.tsx"
GUIDE = ROOT / "apps" / "web" / "app" / "guided-workflow" / "page.tsx"
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"


def test_legacy_start_job_route_redirects_to_unified_assessment() -> None:
    source = START_JOB.read_text(encoding="utf-8")

    assert 'import {redirect} from "next/navigation"' in source
    assert 'redirect("/assessment?tier=express#assessment")' in source
    assert "localStorage" not in source
    assert "Save job" not in source
    assert "Authorization scope" not in source


def test_easy_mode_uses_run_a_job_without_duplicate_scope_form() -> None:
    source = EASY.read_text(encoding="utf-8")

    assert 'href="/assessment?tier=express#assessment"' in source
    assert '"/assessment?tier=comprehensive#assessment"' in source
    assert '"/assessment?tier=mid#assessment"' not in source
    assert 'href="/start-job"' not in source
    assert '"/start-job"' not in source
    assert "Enter the repository once" in source
    assert "Use the checkbox" in source


def test_guide_points_to_single_intake_and_single_authorization_confirmation() -> None:
    source = GUIDE.read_text(encoding="utf-8")

    assert 'href="/assessment?tier=express#assessment"' in source
    assert 'href="/start-job"' not in source
    assert "Use the unified assessment page instead of completing a separate setup wizard." in source
    assert "Use the single authorization checkbox" in source
    assert "Enter each fact once" in source


def test_unified_assessment_retains_minimal_authorized_input_contract() -> None:
    source = ASSESSMENT.read_text(encoding="utf-8")

    for required in (
        "Repository owner/name or GitHub URL",
        "Client name, optional",
        "Project name, optional",
        "I confirm I own this target or have explicit permission to assess it.",
        'type Service = "express" | "comprehensive"',
        '`${text.run} ${copy.label}`',
    ):
        assert required in source
    assert "Authorized by" not in source
    assert "Authorization scope" not in source
    assert "Save job" not in source
