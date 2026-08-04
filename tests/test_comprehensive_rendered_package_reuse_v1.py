from __future__ import annotations

import base64
import io

from reportlab.pdfgen import canvas

from nico.comprehensive_rendered_package_reuse_v1 import (
    install_comprehensive_rendered_package_reuse_v1,
)


def _pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(40, 760, "Evidence-Bound Technical Review Package")
    document.showPage()
    document.save()
    return buffer.getvalue()


def test_complete_canonical_render_is_not_replaced_by_legacy_renderer() -> None:
    from nico import client_report_completion_v2 as completion

    install_comprehensive_rendered_package_reuse_v1()
    package = {
        "json": {"identity": {"repository": "BoneManTGRM/NICO"}},
        "markdown": "# NICO\n\nAUTOMATED DRAFT\n",
        "html": "<html><body>AUTOMATED DRAFT</body></html>",
        "pdf_base64": base64.b64encode(_pdf()).decode("ascii"),
        "premium_report_renderer": {"dark_branded_cover_restored": True},
        "client_report_completion": {},
    }

    result = completion.legacy.finalize_client_report_package(package)

    assert result["pdf_base64"] == package["pdf_base64"]
    assert result["markdown"] == package["markdown"]
    assert result["html"] == package["html"]
    assert result["client_report_completion"]["legacy_rerender_skipped"] is True
    assert result["client_report_completion"]["canonical_rendered_bytes_preserved"] is True
    assert result["client_report_completion"]["client_delivery_allowed"] is False
