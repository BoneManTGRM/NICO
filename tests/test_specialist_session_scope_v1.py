from __future__ import annotations

from nico.admin_security import require_admin_write
from nico.specialist_access_v1 import (
    SPECIALIST_SCOPE,
    issue_specialist_session,
    validate_specialist_session,
)


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

    specialist_status = validate_specialist_session(token)
    assert specialist_status is not None
    assert specialist_status["authority"] == "nico_comprehensive_operator"
    assert specialist_status["scope"] == SPECIALIST_SCOPE
    assert specialist_status["scope"] != "nico_admin"
