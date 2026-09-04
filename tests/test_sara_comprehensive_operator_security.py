from nico.admin_security import require_admin_write, require_comprehensive_operator


def test_sara_password_is_scoped_to_comprehensive_operator(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "master-admin-password")
    monkeypatch.setenv("NICO_SARA_OPERATOR_PASSWORD", "sara-own-operator-password")

    allowed, status = require_comprehensive_operator("sara-own-operator-password")
    assert allowed is True
    assert status["authority"] == "sara_comprehensive_operator"
    assert status["scope"] == "comprehensive_review_and_delivery"
    assert "sara-own-operator-password" not in repr(status)

    admin_allowed, admin_status = require_admin_write("sara-own-operator-password")
    assert admin_allowed is False
    assert "sara-own-operator-password" not in repr(admin_status)


def test_comprehensive_operator_fails_closed_without_exact_password(monkeypatch):
    monkeypatch.delenv("NICO_SARA_OPERATOR_PASSWORD", raising=False)
    allowed, status = require_comprehensive_operator("sara-own-operator-password")
    assert allowed is False
    assert status["status"] == "unavailable"


def test_master_admin_and_process_local_authority_remain_supported(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "master-admin-password")
    allowed, status = require_comprehensive_operator("master-admin-password")
    assert allowed is True
    assert status["authority"] == "nico_admin"


def test_legacy_fast_hash_verifier_is_not_accepted(monkeypatch):
    monkeypatch.delenv("NICO_SARA_OPERATOR_PASSWORD", raising=False)
    monkeypatch.setenv(
        "NICO_SARA_OPERATOR_PASSWORD_SHA256",
        "282e0db5774a2613bf34e5bc25fde8df2ea180c59b261495cd67ba1d40e1207a",
    )

    allowed, status = require_comprehensive_operator(
        "a-strong-machine-password-kept-only-by-sara"
    )
    assert allowed is False
    assert status["configured"] is False
