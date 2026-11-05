from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

EN='decision: Proceed to professional human review; automated synthesis is not stakeholder approval, residual-risk acceptance, final approval, or client-delivery authorization.'
ES='Decisión: Proceder a revisión humana profesional; la síntesis automatizada no constituye aprobación de las partes interesadas, aceptación del riesgo residual, aprobación final ni autorización de entrega al cliente.'


def _worker():
    import base64,io
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from nico import comprehensive_spanish_canonical_report_v87 as spanish
    from tests.test_v2_premium_report_renderer import _package
    from pypdf import PdfReader
    package=_package('es-MX')
    stage={'stage_id':'risk_reduction_and_executive_briefing','title':'Risk Reduction and Executive Briefing','status':'review_required','summary':'The automated executive briefing and bounded priority register are complete for review; finding acceptance, residual-risk ownership, and remediation commitment remain pending human disposition.','evidence':[EN]}
    package['json']['stage_summaries']=[stage]
    original=deepcopy(package);result=rebuild_client_artifacts(package);_validate_exact_artifact_hashes(result)
    text=' '.join(' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages).split())
    assert ES in text
    assert 'decision: Proceder' not in text
    protected={'stage_id':'client_human_evidence_stakeholder_context','evidence':['Dato aportado por el cliente · Decisiones: '+EN]}
    assert spanish._localize_tree(protected)==protected
    assert package==original
    assert result['client_delivery_allowed'] is False and result['human_review_required'] is True


def test_installed_generated_decision_key_and_protected_literal(tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root=Path(__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c','from tests.test_spanish_generated_decision_key import _worker; _worker()'],cwd=root,env=owned_worker_environment(root,tmp_path,os.environ),capture_output=True,text=True,timeout=120)
    assert run.returncode==0,run.stdout+run.stderr
