from __future__ import annotations

from nico.admin_security import (
    admin_write_status,
    internal_admin_token,
    require_admin_write,
    safe_public_admin_status,
)


def test_internal_authority_is_accepted_without_operator_configuration(monkeypatch):
    monkeypatch.delenv("NICO_ADMIN_TOKEN", raising=False)

    token = internal_admin_token()
    allowed, status = require_admin_write(token)

    assert token
    assert allowed is True
    assert status["status"] == "internal"
    assert status["publicly_usable"] is False


def test_internal_authority_is_not_disclosed_as_public_admin_configuration(monkeypatch):
    monkeypatch.delenv("NICO_ADMIN_TOKEN", raising=False)

    operator_status = admin_write_status(None)
    public_status = safe_public_admin_status()

    assert operator_status["enabled"] is False
    assert operator_status["status"] == "read_only"
    assert public_status["admin_writes_configured"] is False
    assert public_status["admin_writes_publicly_enabled"] is False
    assert internal_admin_token() not in repr(public_status)


def test_random_or_missing_public_token_remains_blocked(monkeypatch):
    monkeypatch.delenv("NICO_ADMIN_TOKEN", raising=False)

    missing_allowed, missing = require_admin_write("")
    random_allowed, random = require_admin_write("not-the-process-local-token")

    assert missing_allowed is False
    assert random_allowed is False
    assert missing["mode"] == "read_only"
    assert random["mode"] == "read_only"


def test_configured_operator_token_still_works_independently(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "operator-secret")

    operator_allowed, operator = require_admin_write("operator-secret")
    internal_allowed, internal = require_admin_write(internal_admin_token())

    assert operator_allowed is True
    assert operator["status"] == "enabled"
    assert internal_allowed is True
    assert internal["status"] == "internal"
