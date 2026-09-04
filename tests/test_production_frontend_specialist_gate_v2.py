from __future__ import annotations

import pytest

from scripts.production_frontend_release_identity import (
    ReleaseIdentityError,
    verify_assessment_page,
)


def test_english_specialist_login_is_a_valid_production_access_boundary():
    page = {
        "url": "https://app.nicoaudit.com/assessment",
        "http_status": 200,
        "html": (
            '<input type="password" />'
            "Cybersecurity specialist access Operator password Open NICO"
        ),
    }
    evidence = verify_assessment_page(locale="en", page=page)
    assert evidence["verified"] is True
    assert evidence["authentication_gate_verified"] is True
    assert evidence["presentation_mode"] == "specialist_authentication_gate"
    assert evidence["workspace_markers_verified"] is False


def test_spanish_specialist_login_is_a_valid_production_access_boundary():
    page = {
        "url": "https://app.nicoaudit.com/es/assessment",
        "http_status": 200,
        "html": (
            '<input type="password" />'
            "Acceso para especialistas en ciberseguridad "
            "Contraseña del operador Abrir NICO"
        ),
    }
    evidence = verify_assessment_page(locale="es-MX", page=page)
    assert evidence["verified"] is True
    assert evidence["authentication_gate_verified"] is True
    assert evidence["presentation_mode"] == "specialist_authentication_gate"


def test_partial_or_stale_gate_fails_closed():
    with pytest.raises(ReleaseIdentityError):
        verify_assessment_page(
            locale="en",
            page={
                "url": "https://app.nicoaudit.com/assessment",
                "http_status": 200,
                "html": "Cybersecurity specialist access",
            },
        )
