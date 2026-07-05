from pathlib import Path


ASSESSMENT = Path("nico/assessment.py")


def test_assessment_wires_express_pack_output():
    content = ASSESSMENT.read_text(encoding="utf-8")
    assert "write_express_assessment_pack" in content
    assert "express_pack" in content
    assert "Express pack error" in content
