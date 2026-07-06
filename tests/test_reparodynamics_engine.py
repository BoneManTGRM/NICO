from nico.report_accuracy import apply_report_accuracy
from nico.reports import build_report_package


def test_reparodynamic_metrics_are_attached_to_guarded_reports():
    guarded = apply_report_accuracy({
        "status": "complete",
        "sections": [
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 85,
                "status": "green",
                "summary": "CI evidence exists.",
                "evidence": ["GitHub Actions workflows found: .github/workflows/ci.yml."],
                "findings": [],
                "unavailable": ["Workflow run history unavailable: GitHub returned 429."],
            }
        ],
    })
    loop = guarded["reparodynamics"]
    assert loop["loop"] == ["detect", "classify", "prioritize", "repair_plan", "approval", "verify", "trend", "stabilize"]
    assert loop["repair_pressure"] > 0
    assert loop["stabilization_score"] < 1
    assert guarded["sections"][0]["confidence"] == "limited"


def test_report_package_surfaces_reparodynamic_loop():
    package = build_report_package({
        "client_name": "Client",
        "project_name": "Project",
        "repository": "owner/repo",
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 72,
                "status": "yellow",
                "summary": "Dependency evidence was inspected.",
                "evidence": ["requirements.txt found with 4 active dependency lines.", "OSV returned no vulnerability records for 4 pinned dependency query/queries."],
                "findings": [],
                "unavailable": [],
            }
        ],
    })
    markdown = package["formats"]["markdown"]
    assert "Reparodynamic Repair Loop" in markdown
    assert "Detection strength" in markdown
    assert package["reparodynamics"]["detection_strength"] > 0
