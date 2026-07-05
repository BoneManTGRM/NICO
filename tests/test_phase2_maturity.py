def test_html_contains_sections():
    # Run assessment first
    run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_maturity_test")
    html_path = Path("/tmp/nico_maturity_test/assessment_latest.html")
    content = html_path.read_text(encoding="utf-8")
    assert "Maturity" in content
    assert "Dependency Audit" in content
    assert "CI/CD Audit" in content
    assert "Architecture & Debt" in content