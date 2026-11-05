"""Public synthetic population matching M3's 5 required / 4 excluded shape."""
from copy import deepcopy
import io
import os
from pathlib import Path
import subprocess
import sys
import pytest
from pypdf import PdfReader


def population():
    required=[dict(scanner_name=name,applicable=True,completed=True,verified=True,status='completed') for name in ('eslint','gitleaks','semgrep','trufflehog')]
    required.append(dict(scanner_name='bandit',applicable=None,completed=True,verified=True,status='completed'))
    excluded=[dict(scanner_name=name,applicable=False,completed=False,verified=False,status='not_applicable',applicability_reason='Synthetic complete snapshot excludes this input.') for name in ('pip-audit','npm-audit','osv-scanner','typescript')]
    return required,excluded


def canonical(language):
    from tests.test_v2_premium_report_renderer import _package
    package=_package(language); c=package['json']; required,excluded=population()
    c.update(requested_scanner_records=required+excluded,scanner_execution_records=required,not_applicable_scanner_records=excluded)
    return package


def check(text,spanish):
    text=' '.join(text.split())
    assert ('Se completaron 5 de 5 ejecuciones requeridas' if spanish else '5 of 5 required scanner executions completed') in text
    assert ('aplicabilidad no comprobada: 1; no aplicables: 4.' if spanish else 'applicability unproven: 1; not applicable: 4.') in text


@pytest.mark.parametrize('spanish',[False,True])
@pytest.mark.parametrize('renderer',['phase1','legacy'])
def test_client_summary_includes_exclusions_without_execution_credit(spanish,renderer):
    from nico.candidate_phase1_report_workload_pdf_v1 import render_phase1_evidence_review_gate_pdf
    from nico.comprehensive_client_ready_projection_v1 import render_evidence_review_gate_pdf
    c=canonical('es-MX' if spanish else 'en')['json']; before=deepcopy(c)
    render=render_phase1_evidence_review_gate_pdf if renderer=='phase1' else render_evidence_review_gate_pdf
    pdf=render(c,{},spanish=spanish)
    check(' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf)).pages),spanish)
    assert c==before


def _worker(language):
    import base64
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    import hashlib
    import tempfile
    from nico.node_scanner_applicability_v1 import inspect_node_inputs, observation_bytes, SOURCE_REASONS
    from nico.scanner_package_inventory_v1 import inspect_package_sources
    package=canonical(language)
    # This synthetic repository contains JS only; remove the template's TS finding path.
    package['json']['canonical_findings'][0]['location']='application.js:1'
    with tempfile.TemporaryDirectory() as directory:
        checkout=Path(directory)
        (checkout/'application.js').write_text('const synthetic = 1;')
        sha=package['json']['identity']['commit_sha']
        inventory=inspect_node_inputs(checkout,sha)
        packages=inspect_package_sources(checkout,sha)
    for record in package['json']['requested_scanner_records']:
        record.update(commit_sha=sha, exact_commit_match=True, artifact_hash='b'*64,
                      raw_artifact_retention_complete=True)
        if record['applicable'] is False:
            name=record['scanner_name']
            if name=='osv-scanner':
                record.update(applicability_evidence=packages)
                continue
            record.update(applicability_evidence=inventory, applicability_reason=SOURCE_REASONS[name],
                          raw_artifact_sha256=hashlib.sha256(observation_bytes(inventory,name)).hexdigest())
    before=deepcopy(package)
    result=rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    texts=[p.extract_text() or '' for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages]
    heading='El triaje técnico y la disposición humana están separados' if language=='es-MX' else 'Technical triage and human disposition are separate'
    pages=[text for text in texts if heading in ' '.join(text.split())]
    assert len(pages)==1
    check(pages[0],language=='es-MX')
    assert package==before
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False


@pytest.mark.parametrize('language',['en','es-MX'])
def test_installed_final_summary_keeps_full_scanner_population(language,tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c','from tests.test_client_summary_scanner_population import _worker; import sys; _worker(sys.argv[1])',language],cwd=root,env=owned_worker_environment(root,tmp_path,os.environ),capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
