"""Actual owned analyzer traces plus bounded verifier perturbations."""
import copy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from nico.assessment_cpp_header_evidence import validate_header_trace

FIXTURE = Path(__file__).parent / 'fixtures/cpp/header-token-evidence-v15'


def sample(index=0):
    metadata = json.loads((FIXTURE / 'bindings.json').read_bytes())
    row = metadata['records'][index]
    raw = (FIXTURE / row['trace']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    return raw, {'source':row['source'], 'locations':row['locations'], 'standard':row['standard']}


@pytest.mark.parametrize('index', [0,1])
def test_actual_active_generated_macro_only_and_unvisited_headers_are_distinct(index):
    raw, args = sample(index)
    proof = validate_header_trace(raw, **args)
    assert proof['normal_pass_completed'] and proof['physical_token_origin_verified']
    active, unvisited = ('active_a.h','active_b.h') if index == 0 else ('active_b.h','active_a.h')
    assert any(p.endswith('/'+active) for p in proof['normal_pass_token_files'])
    assert any(p.endswith('/'+unvisited) for p in proof['unvisited_files'])
    assert any(p.endswith('/generated/generated.h') for p in proof['normal_pass_token_files'])
    assert any(p.endswith('/macro_only.h') for p in proof['include_observed_files'])
    assert not any(p.endswith('/macro_only.h') for p in proof['parsed_token_files'])
    assert any(p.endswith('/unvisited.h') for p in proof['unvisited_files'])
    assert proof['line_or_branch_coverage_inferred'] is False
    assert proof['individual_checker_coverage_inferred'] is False


def test_real_logical_alias_cannot_credit_the_macro_only_header_as_parsed():
    raw, args = sample(2)
    proof = validate_header_trace(raw, **args)
    assert proof['normal_pass_completed'] is True
    assert proof['physical_token_origin_verified'] is False
    assert proof['parsed_token_files'] == proof['normal_pass_token_files'] == []
    assert proof['limitations'] == ['logical_locations_remapped_physical_token_origin_unproven']


@pytest.mark.parametrize('index',[0,1,2])
def test_original_actual_default_analyzer_dialect_mismatch_rejects(index):
    unused, args = sample(index)
    with pytest.raises(ValueError, match='standard_mismatch'):
        validate_header_trace((FIXTURE/f'original-{index}.xml').read_bytes(),**args)


@pytest.mark.parametrize('fault', ['wrong_source','wrong_standard','missing_footer','duplicate_configuration',
    'missing_stage','stage_order','false_completion','overflow','invalid_tokens','malformed_boolean',
    'unbound_token','token_not_entered','unbound_include','unvisited_parent','wrong_cfg',
    'impossible_shared_population','unknown_element','dtd','oversized','truncated'])
def test_missing_corrupt_mismatched_and_false_completion_evidence_rejects(fault):
    raw,args=sample();args=copy.deepcopy(args);doc=ET.fromstring(raw);cfg=doc.find('configuration')
    if fault=='wrong_source': args['source']=next(p for p in args['locations'] if p.endswith('/unvisited.h'))
    elif fault=='wrong_standard':args['standard']='c++20'
    elif fault=='missing_footer':doc.remove(doc.find('file_end'))
    elif fault=='duplicate_configuration':doc.insert(1,copy.deepcopy(cfg))
    elif fault=='missing_stage':cfg.remove(cfg.findall('token_membership')[1])
    elif fault=='stage_order':cfg.findall('token_membership')[0].set('stage','normal_form_ast_validated')
    elif fault=='false_completion':cfg.set('checks_completed','false')
    elif fault in {'overflow','invalid_tokens','malformed_boolean'}:
        cfg.findall('token_membership')[0].set('overflow' if fault=='overflow' else 'invalid',
            'maybe' if fault=='malformed_boolean' else 'true')
    elif fault=='unbound_token':cfg.findall('token_membership')[0].find('token_file').set('file','/unbound/header.h')
    elif fault=='token_not_entered':
        p=next(p for p in args['locations'] if p.endswith('/unvisited.h'))
        cfg.findall('token_membership')[0].find('token_file').set('file',p)
        cfg.findall('token_membership')[1].find('token_file').set('file',p)
    elif fault=='unbound_include':cfg.find('include').set('file','/unbound/header.h')
    elif fault=='unvisited_parent':
        cfg.findall('include')[1].set('parent',next(p for p in args['locations'] if p.endswith('/unvisited.h')))
    elif fault=='wrong_cfg':cfg.set('cfg','MODE=2')
    elif fault=='impossible_shared_population':
        for event in cfg.findall('include'):cfg.remove(event)
        names=['/work/source/h'+str(i)+'.h' for i in range(2047)]
        for p in names:
            args['locations'][p]=('original',p,'0'*64)
            cfg.insert(1,ET.Element('include',file=p,parent=args['source'],kind='include',entered='true'))
        for stage in cfg.findall('token_membership'):
            for child in list(stage):stage.remove(child)
            for p in sorted([args['source'],*names]):ET.SubElement(stage,'token_file',file=p)
    elif fault=='unknown_element':ET.SubElement(cfg.find('effective'),'untrusted',value='x')
    mutated=ET.tostring(doc)
    if fault=='dtd':mutated=b'<!DOCTYPE nico_native [<!ENTITY x "x">]>'+mutated
    elif fault=='oversized':mutated=b'x'*(1024*1024+1)
    elif fault=='truncated':mutated=mutated[:-12]
    with pytest.raises(ValueError):validate_header_trace(mutated,**args)


@pytest.mark.parametrize('disposition',['preprocess_error','terminated','internal_error'])
def test_real_producer_error_dispositions_remain_truthfully_incomplete(disposition):
    raw,args=sample();doc=ET.fromstring(raw);cfg=doc.find('configuration')
    cfg.set('disposition',disposition);cfg.set('checks_completed','false');cfg.set('completed','false')
    proof=validate_header_trace(ET.tostring(doc),**args)
    assert proof['normal_pass_completed'] is False
    assert proof['normal_pass_token_files'] == []


@pytest.mark.parametrize('encoding', ['utf-16', 'utf-16-le', 'utf-16-be'])
def test_non_utf8_dtd_cannot_credit_an_actual_header_trace(encoding):
    raw, args = sample()
    text = ET.tostring(ET.fromstring(raw), encoding='unicode')
    supplied = ('<!DOCTYPE nico_native [<!ENTITY x "owned">]>' + text).encode(encoding)
    with pytest.raises(ValueError, match='worker_project_header_evidence_invalid'):
        validate_header_trace(supplied, **args)
