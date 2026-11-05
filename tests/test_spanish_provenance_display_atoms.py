"""Generated provenance display atoms; raw retained records stay byte-identical."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import pytest


def provenance():
    return {'backend_build_commit':'a'*40,'frontend_build_commit':'b'*40,
        'scanner_execution_evidence':{'scanner_records':[
          {'scanner_name':'eslint','scanner_version':'literal-status=True','execution_status':'completed',
           'execution_evidence_verified':True,'retained_ci_evidence_verified':False,'execution_observed':True,
           'inapplicability_evidence_verified':False,'raw_artifact':{'sha256':'c'*64,'availability':'available'},
           'execution_provenance':{'execution_receipt':{'receipt_sha256':'d'*64,'status':'verified'}},'configuration':{}},
          {'scanner_name':'typescript','execution_status':'not_applicable','raw_artifact':{},'configuration':{}}]}}


def _worker(language):
    import base64,io
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_v2_premium_report_renderer import _package
    from pypdf import PdfReader
    package=_package(language);raw=provenance()
    package['json']['assessment']['nico_release_provenance']=deepcopy(raw)
    before=deepcopy(package);result=rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    text=' '.join(' '.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages).split())
    if language=='es-MX':
        for value in ('eslint: completado;', 'typescript: no aplicable;', 'disponibilidad=disponible', 'estado=verificado', 'configuración completa verificada=No'):
            assert value in text,value
        assert 'verificada=True' not in text and 'verificada=False' not in text
    else:
        assert 'eslint: completed;' in text and 'availability=available' in text
    assert 'literal-status=True' in text and 'c'*64 in text and 'd'*64 in text
    assert package==before
    assert result['json']['assessment']['nico_release_provenance']==raw
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False


@pytest.mark.parametrize('language',['en','es-MX'])
def test_installed_final_provenance_translates_only_authored_atoms(language,tmp_path):
    from tests.owned_worker_environment import owned_worker_environment
    root=Path(__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-c','from tests.test_spanish_provenance_display_atoms import _worker; import sys; _worker(sys.argv[1])',language],cwd=root,env=owned_worker_environment(root,tmp_path,os.environ),capture_output=True,text=True,timeout=120)
    assert run.returncode==0,run.stdout+run.stderr


def test_typed_receipt_and_unknown_values_are_not_rewritten():
    from nico.comprehensive_release_provenance_v1 import _provenance_lines
    raw=provenance();row=raw['scanner_execution_evidence']['scanner_records'][0]
    row['execution_provenance']['execution_receipt']['status']='retained_receipt_integrity_verified'
    row['raw_artifact']['availability']='verified'
    before=deepcopy(raw)
    text=' '.join(value for _,value in _provenance_lines(raw,spanish=True))
    assert 'estado=integridad del comprobante conservado verificada' in text
    assert 'disponibilidad=verificado' in text
    assert raw==before
    row['execution_status']='future_status_preserve'
    assert any('future_status_preserve' in value for _,value in _provenance_lines(raw,spanish=True))
