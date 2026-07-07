from pathlib import Path


def test_operator_hub_links_to_setup_workflow_pages():
    page = Path("apps/web/app/operator/page.tsx").read_text(encoding="utf-8")

    assert "/coverage-targets" in page
    assert "/setup-readiness" in page
    assert "/setup-actions" in page
    assert "/final-review" in page
    assert "Max-coverage path" in page
