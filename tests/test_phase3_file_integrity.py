def test_reporting_contains_dependency_details():
    with open(REPORTING, "r", encoding="utf-8") as f:
        content = f.read()
    assert "dependency_details" in content