from __future__ import annotations

import subprocess
import sys
import textwrap


def test_final_spanish_worker_localizes_long_evidence_before_layout() -> None:
    # Production renders the final report in an isolated child process. Exercise the
    # same clean import boundary here so unrelated pytest installer order cannot mask
    # or reintroduce a post-layout translation wrapper.
    probe = textwrap.dedent(
        r"""
        import base64
        import io

        from pypdf import PdfReader
        from reportlab.pdfbase.pdfmetrics import stringWidth

        from nico.api import final_report_worker_bootstrap as worker
        from nico import phase17_canonical_artifact_rebuild_v1 as phase17
        from tests.test_v2_premium_report_renderer import _package


        def text_bound_violations(pdf):
            reader = PdfReader(io.BytesIO(pdf))
            violations = []
            for page_number, page in enumerate(reader.pages, start=1):
                left = float(page.mediabox.left)
                right = float(page.mediabox.right)

                def visit(text, cm, tm, font, font_size):
                    value = str(text or "").rstrip("\n")
                    if not value:
                        return
                    font_name = str((font or {}).get("/BaseFont") or "/Helvetica")
                    font_name = font_name.split("+")[-1].lstrip("/") or "Helvetica"
                    try:
                        width = stringWidth(value, font_name, font_size)
                    except Exception:
                        width = stringWidth(value, "Helvetica", font_size)
                    origin = cm[4] + (tm[4] * cm[0]) + (tm[5] * cm[2])
                    scale = abs((tm[0] * cm[0]) + (tm[1] * cm[2])) or 1.0
                    edge = origin + (width * scale)
                    if origin < left - 0.5 or edge > right + 0.5:
                        violations.append((page_number, origin, edge, value))

                page.extract_text(visitor_text=visit)
            return violations


        assert worker.FINAL_REPORT_WORKER_RUNTIME["status"] == "ready"
        package = _package("es-MX")
        package["json"]["scanner_execution_records"] = [
            {
                "scanner_name": scanner,
                "state": "completed",
                "status": "completed",
                "completed": True,
                "verified": True,
                "exact_commit_match": True,
                "artifact_hash": "b" * 64,
                "findings": [],
            }
            for scanner in (
                "pip-audit",
                "npm-audit",
                "osv-scanner",
                "bandit",
                "semgrep",
                "eslint",
                "typescript",
                "gitleaks",
                "trufflehog",
            )
        ]
        package["json"]["stage_summaries"] = [
            {
                "stage_id": "risk_reduction_and_executive_briefing",
                "title": "Risk Reduction and Executive Briefing",
                "status": "complete",
                "summary": (
                    "The automated executive synthesis and bounded priority register are "
                    "complete for review; client acceptance remains human-only."
                ),
                "evidence": [
                    "top_technical_priorities[0].reason: Snapshot-bound source footprint "
                    "and measured complexity evidence were evaluated without score override."
                ],
            }
        ]

        result = phase17.rebuild_client_artifacts(package)
        pdf = base64.b64decode(result["pdf_base64"])
        reader = PdfReader(io.BytesIO(pdf))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        normalized = " ".join(text.split())

        assert text_bound_violations(pdf) == []
        assert "pip-audit: ejecución completada; commit exacto=sí" in normalized
        assert (
            "top_technical_priorities[0].reason: Se evaluaron la huella del código fuente "
            "vinculada a la instantánea y la evidencia de complejidad medida sin "
            "sobrescribir la puntuación."
        ) in normalized
        assert "pip-audit: execution completed" not in text
        assert "Snapshot-bound source footprint" not in text
        assert result["human_review_required"] is True
        assert result["client_delivery_allowed"] is False
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
