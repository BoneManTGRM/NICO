"""Current Comprehensive review navigation; no approval or network simulation."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

# Exercise actual helpers without importing browser launchers/dependencies.
def load_helper(filename, function_name):
    source = Path(__file__).resolve().parents[1] / "scripts" / filename
    helper = next(node for node in ast.parse(source.read_text()).body
                  if isinstance(node, ast.FunctionDef) and node.name == function_name)
    namespace = {"Page": Any, "Any": Any, "parse_qs": parse_qs, "urlparse": urlparse}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(source), "exec"), namespace)
    return namespace[function_name]


@pytest.fixture(params=[
    ("mobile_restart_live_acceptance_v1.py", "_mobile_review_locale_surface"),
    ("completed_run_two_pass_acceptance_v1.py", "_review_locale_surface"),
])
def proof(request):
    return load_helper(*request.param)


class ReviewDocument:
    """Minimal DOM contract captured from the actual dedicated review page."""

    def __init__(self, locale: str) -> None:
        self.url = "https://app.nicoaudit.com/operations/final-review?service=comprehensive&run_id=comprun_test&lang=" + locale
        self.language = "es-MX" if locale == "es-MX" else "en"
        self.contract = "final-report-independent-v1"
        self.heading = (
            "Aprueba el informe final exacto de la evaluación."
            if locale == "es-MX" else "Approve the exact final assessment report."
        )

        self.boundary = (
            "Aprobar y descargar registra la aprobación del informe y el permiso de entrega al cliente en una sola acción. La revisión especializada y el control de calidad independiente siguen declarados; no se envía ningún informe automáticamente."
            if locale == "es-MX" else
            "Approve and download records report approval and client-delivery permission in one action. Specialist review and independent QC remain accurately disclosed; no report is sent automatically."
        )

    def locator(self, selector: str):
        return ReviewElement(self, selector)

    def wait_for_function(self, expression, *, arg, timeout):
        # A present element alone cannot establish localized heading or document language.
        selector = re.search(r"main\[data-review-contract='([^']+)'\] h1", expression)
        assert selector and selector[1] == self.contract
        assert self.language.lower().startswith(arg[0])
        assert self.heading == arg[1]

    def evaluate(self, expression):
        assert "document.documentElement.lang" in expression
        return self.language


class ReviewElement:
    def __init__(self, document, selector):
        self.document, self.selector = document, selector

    def wait_for(self, *, state, timeout):
        assert state == "visible"
        expected = "main[data-review-contract='" + self.document.contract + "']"
        if self.selector != expected:
            raise TimeoutError("Requested review workspace is absent")

    def locator(self, selector):
        assert selector == "h1"
        return ReviewElement(self.document, selector)

    def inner_text(self):
        return self.document.heading if self.selector == "h1" else self.document.heading + "\n" + self.document.boundary


@pytest.mark.parametrize("locale", ["en", "es-MX"])
def test_completed_comprehensive_opens_current_review_surface(locale, proof):
    result = proof(ReviewDocument(locale), locale, "comprun_test")
    assert result["heading"] == ReviewDocument(locale).heading
    assert result["run_id_preserved"] is True
    assert result["requested_locale_preserved"] is True


@pytest.mark.parametrize("field,value", [
    ("url", "https://app.nicoaudit.com/operations/final-review?run_id=comprun_other&lang=es-MX"),
    ("url", "https://app.nicoaudit.com/operations/final-review?run_id=comprun_test&lang=en"),
    ("language", "en"),
    ("heading", "Approve the exact final assessment report."),
    ("contract", "accepted-edition-v2"),
])
def test_review_proof_rejects_wrong_run_locale_heading_or_legacy_surface(field, value, proof):
    page = ReviewDocument("es-MX")
    setattr(page, field, value)
    with pytest.raises((AssertionError, TimeoutError)):
        proof(page, "es-MX", "comprun_test")


@pytest.mark.parametrize("locale", ["en", "es-MX"])
def test_desktop_review_requires_current_specialist_and_no_transmission_disclosure(locale):
    page = ReviewDocument(locale)
    page.boundary = ""
    proof = load_helper("completed_run_two_pass_acceptance_v1.py", "_review_locale_surface")
    with pytest.raises(AssertionError):
        proof(page, locale, "comprun_test")
