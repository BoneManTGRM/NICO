from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "docs" / "phase3-acceptance-repair-boundary.txt"


def test_phase3_acceptance_repair_boundary_remains_fail_closed() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")
    assert "Real client mode remains fail closed" in text
    assert "No automated human approval" in text
    assert "client delivery authorization" in text
