"""Execute the production availability policy against retained-status shapes."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx'


def _availability(payload, locale='en'):
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const {stripTypeScriptTypes, createRequire} = require('node:module');
const source = fs.readFileSync(process.argv[1], 'utf8');
const logic = source.slice(source.indexOf('type Decision'), source.indexOf('function stableIdentity'));
const appRequire = createRequire(require('node:path').resolve('apps/web/package.json'));
const compiled = stripTypeScriptTypes ? stripTypeScriptTypes(logic)
  : appRequire('typescript').transpileModule(logic, {compilerOptions:{target:7}}).outputText;
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = {input, output:null};
vm.runInNewContext(compiled + '\noutput = {available: reviewPdfAvailable(input.payload), notice: reviewLoadNotice(input.payload, input.locale)};', context);
process.stdout.write(JSON.stringify(context.output));
"""
    result = subprocess.run(['node', '-e', script, str(SOURCE)], input=json.dumps({'payload':payload,'locale':locale}), text=True, capture_output=True, cwd=ROOT, check=True)
    return json.loads(result.stdout)


def _response():
    return {'status':'blocked','review_artifact_identity':{'artifact_digests':{'pdf':{'sha256':'a'*64}}}}


@pytest.mark.parametrize('locale', ['en','es-MX'])
def test_retained_digest_does_not_claim_a_final_pdf_is_available(locale):
    result = _availability(_response(), locale)
    assert result['available'] is False
    assert ('not available' if locale == 'en' else 'no está disponible') in result['notice']


@pytest.mark.parametrize('reports', [{}, {'pdf_filename':'report.pdf'}, {'pdf_base64':''}, {'pdf_base64':'   '}, {'pdf_base64':123}, {'pdf_available':True,'artifact_delivery':'on_demand_exact_run'}])
def test_metadata_or_manifest_does_not_enable_the_embedded_pdf_download(reports):
    value = _response()
    value['reports'] = reports
    assert _availability(value)['available'] is False


@pytest.mark.parametrize('locale', ['en','es-MX'])
def test_real_pdf_payload_and_identity_can_proceed_to_existing_integrity_validation(locale):
    value = _response()
    value['reports'] = {'pdf_base64':'JVBERi0xLjQK'}
    assert _availability(value, locale)['available'] is True


@pytest.mark.parametrize('digest', ['', 'a'*63, 'not-a-digest'])
def test_bytes_without_exact_digest_do_not_enable_download(digest):
    value = _response()
    value['reports'] = {'pdf_base64':'JVBERi0xLjQK'}
    value['review_artifact_identity']['artifact_digests']['pdf']['sha256'] = digest
    assert _availability(value)['available'] is False


def test_ui_actions_and_success_notice_use_the_same_availability_policy():
    source = SOURCE.read_text()
    assert 'const finalPdfAvailable = reviewPdfAvailable(result);' in source
    assert 'setNotice(reviewLoadNotice(current, locale));' in source
    assert 'if (!operatorReady || !finalPdfAvailable || !result)' in source
    assert 'if (!result || !finalPdfAvailable || !finalActionAuthorityReady' in source
    assert 'disabled={loading || !operatorReady || !finalPdfAvailable}' in source
    assert 'disabled={loading || !finalPdfAvailable || !finalActionAuthorityReady' in source
