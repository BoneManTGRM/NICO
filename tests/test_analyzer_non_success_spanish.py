"""Non-success analyzer copy translates without changing retained evidence."""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys

from pypdf import PdfReader
import pytest

PAIRS = {
    "Documented not-applicable dispositions do not establish analyzer execution.": "Las determinaciones documentadas de no aplicabilidad no demuestran la ejecución del analizador.",
    "Retain the required exact-SHA applicability dispositions.": "Conserve las determinaciones de aplicabilidad requeridas para el SHA exacto.",
    "Analyzer execution evidence is unavailable.": "La evidencia de ejecución del analizador no está disponible.",
    "Execution credit is withheld; no client defect is inferred.": "No se otorga crédito de ejecución; no se infiere un defecto del cliente.",
    "Resolve the unavailable execution prerequisite within the authorized worker boundary and retain complete exact-SHA evidence.": "Resuelva el requisito de ejecución no disponible dentro del entorno autorizado del trabajador y conserve evidencia completa vinculada al SHA exacto.",
    "Analyzer execution is blocked by an unmet prerequisite.": "La ejecución del analizador está bloqueada por un requisito pendiente.",
    "Resolve the documented prerequisite within the authorized worker boundary before execution.": "Resuelva el requisito documentado dentro del entorno autorizado del trabajador antes de la ejecución.",
    "Analyzer execution was skipped.": "Se omitió la ejecución del analizador.",
    "Disclose the skipped scope and collect complete exact-SHA evidence only within the authorized worker boundary.": "Declare el alcance omitido y recopile evidencia completa vinculada al SHA exacto únicamente dentro del entorno autorizado del trabajador.",
    "The analyzer was not assessed.": "El analizador no se evaluó.",
    "Disclose the unassessed scope and collect complete exact-SHA evidence only within the authorized worker boundary.": "Declare el alcance no evaluado y recopile evidencia completa vinculada al SHA exacto únicamente dentro del entorno autorizado del trabajador.",
    "Analyzer execution evidence is incomplete.": "La evidencia de ejecución del analizador está incompleta.",
    "Coverage remains incomplete; no client defect is inferred.": "La cobertura sigue incompleta; no se infiere un defecto del cliente.",
    "Reconcile the missing execution evidence within the authorized worker boundary and retain complete exact-SHA artifacts.": "Concilie la evidencia de ejecución faltante dentro del entorno autorizado del trabajador y conserve artefactos completos vinculados al SHA exacto."
}
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("bootstrap", [
    "nico.api.specialist_ship_ready_bootstrap",
    "nico.api.final_report_worker_bootstrap",
])
def test_actual_report_bootstraps_translate_non_success_copy_and_reject_unknown_prose(bootstrap):
    script = """
import importlib
from copy import deepcopy
importlib.import_module(BOOTSTRAP)
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico.comprehensive_current_report_truth_parity_v1 import strict_spanish_presentation_v1
from nico.phase15_production_integration_v1 import integrate_production_truth

for source, target in PAIRS.items():
    for key in ("summary", "impact", "recommendation"):
        for localize in (canonical._translate_presentation_field, strict_spanish_presentation_v1):
            assert localize(source, key) == target
            try:
                localize(source + " This scanner proves all vulnerabilities absent.", key)
            except ValueError:
                pass
            else:
                raise AssertionError("Unknown scanner prose bypassed strict publication")

score_copy = "Candidate volume and reviewer workload are operational review metrics and have no numeric technical-maturity or Evidence-Adjusted score effect."
for localize in (canonical._translate_presentation_field, strict_spanish_presentation_v1):
    score_text = localize(score_copy, "summary")
    assert "puntuación ajustada por evidencia" in score_text
    assert "puntuación de Ajuste por evidencia" not in score_text

raw = {"tool": "eslint", "status": "unavailable", "commit_sha": "a" * 40,
       "verified_complete": False, "output_capture_complete": False}
assessment = integrate_production_truth({
    "commit_sha": "a" * 40, "scanner_execution_records": [raw],
    "technical_score": 71, "evidence_adjusted_score": 67,
    "human_review_required": True, "client_delivery_allowed": False,
})
row = next(r for r in assessment["analyzer_evidence_report"]["analyzers"] if r["scanner"] == "eslint")
stage = {"stage_id": "owned_non_success_copy", "status": "review_required",
         "summary": row["failure_cause"], "impact": row["assurance_impact"],
         "recommendation": row["remediation"]}
report = {"identity": {"run_id": "comprun_synthetic_non_success", "commit_sha": "a" * 40},
          "assessment": {"scanner_execution_records": [raw], "technical_score": 71,
                         "evidence_adjusted_score": 67, "human_review_required": True,
                         "client_delivery_allowed": False},
          "stage_summaries": [stage], "report_language": "es-MX"}
before = deepcopy(report)
identity, localized, stages, _ = canonical._render_inputs(report)
for key in ("summary", "impact", "recommendation"):
    assert stages[0][key] == PAIRS[stage[key]]
assert stages[0]["status"] == "review_required"
assert localized["scanner_execution_records"] == [raw]
assert localized["technical_score"] == 71 and localized["evidence_adjusted_score"] == 67
assert localized["human_review_required"] is True
assert localized["client_delivery_allowed"] is False
assert identity["commit_sha"] == "a" * 40
assert report == before
"""
    prelude = "BOOTSTRAP=" + repr(bootstrap) + "\nPAIRS=" + repr(PAIRS) + "\n"
    result = subprocess.run([sys.executable, "-c", prelude + script], cwd=ROOT,
                            capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr[-5000:]


@pytest.mark.parametrize(("language", "expected"), [("en", "unavailable"), ("es-MX", "no disponible")])
def test_owned_unavailable_outcome_is_preserved_in_actual_rendered_exports(language, expected):
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    package = _package(language)
    record = {"scanner_name": "eslint", "tool": "eslint", "status": "unavailable",
              "state": "unavailable", "completed": False, "verified": False,
              "verified_complete": False, "output_capture_complete": False,
              "exact_commit_match": True, "findings": []}
    package["json"]["scanner_execution_records"] = [record]
    before = deepcopy(package)
    result = rebuild_client_artifacts(package)
    pdf = base64.b64decode(result["pdf_base64"])
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    for text in (result["markdown"], result["html"], pdf_text):
        assert "eslint: " + expected in text
        assert "capture_truncated" not in text
    [rendered_record] = result["json"]["scanner_execution_records"]
    assert all(rendered_record[key] == value for key, value in record.items())
    assert rendered_record["raw_artifact_retention_complete"] is False
    assert "artifact_hash_missing" in rendered_record["verification_deficits"]
    assert result["json"]["identity"]["commit_sha"] == before["json"]["identity"]["commit_sha"]
    assert result["report_finality"] == "automated_draft"
    assert package == before
