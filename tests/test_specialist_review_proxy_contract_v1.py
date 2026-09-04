from pathlib import Path


def test_signed_session_is_forwarded_to_both_access_and_review_boundaries():
    source = Path(
        "apps/web/app/api/nico/assessment/[...path]/route.ts"
    ).read_text(encoding="utf-8")
    assert 'headers.set("X-NICO-Operator-Session", session)' in source
    assert 'headers.set("X-NICO-Admin-Token", session)' in source
    assert "if (!rawOperatorToken)" in source
    assert 'headers.set("X-NICO-Admin-Token", rawOperatorToken)' in source
