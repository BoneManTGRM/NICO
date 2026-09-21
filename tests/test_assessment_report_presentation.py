"""Run actual frontend presentation modules against bounded synthetic run states."""
from pathlib import Path
import subprocess


def test_assessment_report_presentation_preserves_truth_and_locale() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/js/assessment-report-presentation.test.cjs"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
