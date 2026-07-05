import json
from pathlib import Path

from nico.assessment import run_assessment
from nico.modules.express_pack import PACK_FILENAMES, write_express_assessment_pack


def _sample_result() -> dict:
    return {
        "assessment_id": "assessment_test",
        "target": "./sample-app",
        "tier": "express",
        "status": "completed",
        "findings_count": 3,
        "repairs_count": 2,
        "limitations": ["Local sample assessment; no production access was used."],
        "dependency_audit": {
            "status": "completed",
            "vulnerabilities_found": 1,
            "critical_count": 0,
            "high_count": 1,
            "risky_dependencies": [],
        },
        "cicd_audit": {
            "status": "limited",
            "has_ci": True,
            "workflow_runs_count": 5,
            "failed_runs_recent": 1,
            "success_rate": 80,
            "last_run_status": "success",
        },
        "architecture_audit": {
            "status": "completed",
            "debt_signals": ["Large module detected in service layer"],
        },
        "github_activity": {
            "status": "completed",
            "commit_count": 24,
            "pr_count": 6,
            "active_authors_count": 2,
            "velocity_classification": "medium",
            "consistency_classification": "stable",
        },
        "github_token_health": {
            "status": "completed",
            "token_present": True,
            "repo_access": True,
            "contents_access": True,
            "pull_requests_access": True,
            "actions_access": True,
        },
        "maturity": {
            "status": "completed",
            "semaphore": "Yellow",
            "score": 68,
            "drivers": ["High dependency risk"],
            "quick_wins": ["Fix high dependency risk"],
        },
        "roadmap": {
            "status": "completed",
            "phases": {
                "30_days": ["Fix high dependency risk"],
                "60_days": ["Improve evidence links"],
                "90_days": ["Expand CI history analysis"],
            },
        },
        "resourcing": {
            "status": "completed",
            "minimum_team": ["Product Engineer"],
            "recommended_team": ["Product Engineering Architect", "Product Engineer"],
            "aggressive_team": ["Product Engineering Architect", "Product Engineer", "Product Quality Engineer"],
            "rationale": ["Dependency and architecture signals require engineering ownership."],
            "when_retainer_makes_sense": "Recurring drift suggests ongoing support is useful.",
        },
        "synthesis": {
            "status": "completed",
            "overall_evidence_weight": 55,
            "ranked_recommendations": [
                {"title": "Fix high/critical dependency vulnerabilities", "weight": 25, "source": "dependency"},
                {"title": "Review architecture debt signals", "weight": 30, "source": "architecture"},
            ],
        },
    }


def test_express_pack_files_are_created(tmp_path):
    output = tmp_path / "assessment_latest"
    result = write_express_assessment_pack(_sample_result(), str(output))

    assert result["status"] == "completed"
    for filename in PACK_FILENAMES:
        assert (output / filename).exists(), filename


def test_evidence_manifest_is_valid_json_and_evidence_backed(tmp_path):
    output = tmp_path / "assessment_latest"
    write_express_assessment_pack(_sample_result(), str(output))

    manifest = json.loads((output / "evidence_manifest.json").read_text(encoding="utf-8"))
    assert manifest["module_statuses"]["dependency_audit"] == "completed"
    assert manifest["ranked_recommendations_with_evidence"]
    for recommendation in manifest["ranked_recommendations_with_evidence"]:
        assert recommendation["evidence"]["module"]
        assert recommendation["evidence"]["summary"]


def test_no_placeholder_text_in_pack_outputs(tmp_path):
    output = tmp_path / "assessment_latest"
    write_express_assessment_pack(_sample_result(), str(output))

    forbidden = ["placeholder", "fake", "invented"]
    for path in output.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            for word in forbidden:
                assert word not in lowered, f"{word} found in {path.name}"


def test_missing_access_creates_limitations(tmp_path):
    output = tmp_path / "assessment_latest"
    result = _sample_result()
    result.pop("github_token_health")
    result.pop("github_activity")
    result["cicd_audit"] = {"status": "limited", "has_ci": False}

    pack = write_express_assessment_pack(result, str(output))
    limitations_text = (output / "limitations.md").read_text(encoding="utf-8")

    assert "GitHub read-only API access was not fully verified" in limitations_text
    assert "CI/CD configuration or run history is missing" in limitations_text
    assert "velocity analysis is limited" in limitations_text
    assert pack["limitations"]


def test_express_report_contains_required_sections(tmp_path):
    output = tmp_path / "assessment_latest"
    write_express_assessment_pack(_sample_result(), str(output))

    report = (output / "technical_health_report.md").read_text(encoding="utf-8")
    for section in [
        "Maturity",
        "Velocity",
        "Dependencies",
        "CI/CD",
        "Architecture",
        "Roadmap",
        "Resourcing",
    ]:
        assert section in report


def test_run_assessment_writes_standard_reports_and_express_pack(tmp_path):
    output = tmp_path / "assessment_latest"
    result = run_assessment("./nico/test_lab", tier="express", output_dir=str(output))

    reports = result.get("reports")
    assert isinstance(reports, dict)
    assert "express_pack" in reports
    assert reports["express_pack"]["status"] == "completed"

    express_output = output / "express_pack"
    assert express_output.exists()
    assert reports["express_pack"]["output_dir"] == str(express_output)

    for filename in PACK_FILENAMES:
        path = express_output / filename
        assert path.exists(), filename
        assert path.read_text(encoding="utf-8").strip(), filename

    for filename in ["assessment_latest.json", "assessment_latest.md", "assessment_latest.html", "evidence_manifest.json"]:
        path = output / filename
        assert path.exists(), filename
        assert path.read_text(encoding="utf-8").strip(), filename

    standard_manifest = json.loads((output / "evidence_manifest.json").read_text(encoding="utf-8"))
    express_manifest = json.loads((express_output / "evidence_manifest.json").read_text(encoding="utf-8"))
    saved_assessment = json.loads((output / "assessment_latest.json").read_text(encoding="utf-8"))

    assert "total_evidence_weight" in standard_manifest
    assert "generated_at" in express_manifest
    assert standard_manifest != express_manifest
    assert saved_assessment["reports"]["express_pack"]["status"] == "completed"
    assert saved_assessment["reports"]["express_pack"]["output_dir"] == str(express_output)

    forbidden = ["placeholder", "fake", "invented"]
    for path in output.rglob("*"):
        if path.is_file():
            lowered = path.read_text(encoding="utf-8").lower()
            for word in forbidden:
                assert word not in lowered, f"{word} found in {path.name}"


def test_express_pack_fallback_language_is_client_facing(tmp_path):
    output = tmp_path / "assessment_latest"
    minimal = {
        "assessment_id": "assessment_minimal",
        "target": "./sample-app",
        "tier": "express",
        "status": "completed",
        "findings_count": 0,
        "repairs_count": 0,
        "limitations": [],
    }
    write_express_assessment_pack(minimal, str(output))

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file()
    )
    forbidden_phrases = [
        "produced by the module",
        "produced by synthesis",
        "available modules",
        "Minimum Team: \n",
        "Recommended Team: \n",
        "Aggressive Team: \n",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined
    assert "Not available from current evidence" in combined
