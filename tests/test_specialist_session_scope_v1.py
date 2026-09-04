from __future__ import annotations

from nico.admin_security import require_admin_write, require_comprehensive_operator
from nico.specialist_access_v1 import issue_specialist_session


def test_signed_specialist_session_is_scoped_below_admin(monkeypatch):
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "operator-password")
    monkeypatch.setenv(
        "NICO_OPERATOR_SESSION_SIGNING_SECRET",
        "specialist-session-scope-test-secret",
    )
    token, _ = issue_specialist_session(
        {"authority": "nico_comprehensive_operator"}
    )

    admin_allowed, admin_status = require_admin_write(token)
    assert admin_allowed is False
    assert admin_status["mode"] == "read_only"

    specialist_allowed, specialist_status = require_comprehensive_operator(token)
    assert specialist_allowed is True
    assert specialist_status["authority"] == "nico_comprehensive_operator"
    assert specialist_status["scope"] == "comprehensive_review_and_delivery"
