"""Physical header membership from the pinned analyzer's executed token pass.

An include event is not parsing. Token labels after AST validation and a
completed normal pass establish only file membership in that pass. Logical
location remapping withholds physical token attribution; no line coverage or
individual-checker coverage is inferred.
"""
from __future__ import annotations

import hashlib
import json
import re
from xml.etree import ElementTree as ET

HEADER_SCHEMA = 'nico.cppcheck-header-token-pass.v2'
HEADER_LIMIT = 1024 * 1024
HEADER_TOOL_MANIFEST_SHA256 = 'cbe13e1183c4e44e398943bcbbe2c68e2cebd984f1bbe694d245a3b7a765f5f4'
HEADER_APPLIER_SHA256 = '9f3261e77b3c75154f67ed23eac5001d988ff46363ffd0cecd763e77e6d34fdc'
_CONFIGURATION_FIELDS = {'cfg', 'disposition', 'checks_completed', 'completed',
    'preprocessing_returned', 'preprocessing_had_output', 'observation_overflow',
    'token_logical_remap_observed', 'normal_pass_started'}
_STAGES = ('pre_simplification', 'normal_form_ast_validated')
_KINDS = {'include', 'forced', 'forced_not_loaded', 'missing', 'depth_skipped', 'pragma_once_skipped'}


def _require(condition, reason='worker_project_header_evidence_invalid'):
    if not condition:
        raise ValueError(reason)


def _boolean(value):
    _require(value in {'true', 'false'})
    return value == 'true'


def validate_header_tool_receipt(raw):
    _require(isinstance(raw, bytes) and 0 < len(raw) <= 65536)
    def unique(pairs):
        result = {}
        for key, item in pairs:
            _require(key not in result)
            result[key] = item
        return result
    try:
        value = json.loads(raw.decode('utf-8','strict'),object_pairs_hook=unique,
            parse_constant=lambda value: _require(False))
    except (ValueError,UnicodeError) as error:
        raise ValueError('worker_project_header_evidence_invalid') from error
    _require(isinstance(value, dict) and set(value) == {'schema','manifest_sha256','upstream_commit',
        'patch_sha256','sources','trace_schema','application_script_sha256','base_tool_version','qualification_completed'})
    _require(value['schema'] == 'nico.cppcheck-header-tool.v1'
        and value['manifest_sha256'] == HEADER_TOOL_MANIFEST_SHA256
        and value['upstream_commit'] == 'ac9db3069b9f90e81e126a090b99ad456e122cf8'
        and value['patch_sha256'] == 'd817eae3b4de2bf08046005218b6d225647a0f6c393dbb93e1de1a426b2d114e'
        and value['trace_schema'] == HEADER_SCHEMA and value['application_script_sha256'] == HEADER_APPLIER_SHA256
        and value['base_tool_version'] == '2.17.1' and value['qualification_completed'] is False
        and hashlib.sha256(json.dumps(value['sources'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
            == '1f2d5601365eededad875f01408f494d00df79e7f2d478fc9fdf2286a78d7b77')
    return value


def header_summary(analysis):
    """Bounded projection; whole-population completeness remains separate."""
    result={}
    for key,empty in [('header_context_evidence',[]),('header_population',{}),('header_unvisited_files',[])]:
        values=analysis.get(key,empty)
        result[key+'_count']=len(values)
        result[key+'_sha256']=hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result.update(header_context_evidence_complete=analysis.get('header_context_evidence_complete') is True,
        header_population_complete=analysis.get('header_population_complete') is True,
        header_tool_manifest_sha256=analysis.get('header_tool_manifest_sha256'))
    return result


def validate_header_trace(raw, *, source, locations, standard, configuration_defines=None,
                          effective_inputs=None):
    """Bind raw native bytes to one configured source and immutable inputs."""
    _require(isinstance(raw, bytes) and 0 < len(raw) <= HEADER_LIMIT)
    try:
        text = raw.decode('utf-8', 'strict')
    except UnicodeError as error:
        raise ValueError('worker_project_header_evidence_invalid') from error
    # The pinned producer emits UTF-8. Reject NUL-bearing alternative XML
    # encodings before ElementTree can auto-detect and parse declarations.
    _require('\x00' not in text and '<!DOCTYPE' not in text.upper()
        and '<!ENTITY' not in text.upper())
    _require(isinstance(source, str) and source in locations and isinstance(locations, dict)
        and isinstance(standard, str) and standard in {'c89', 'c99', 'c11', 'c17', 'c23',
            'c++03', 'c++11', 'c++14', 'c++17', 'c++20', 'c++23', 'c++26'})
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, UnicodeError) as error:
        raise ValueError('worker_project_header_evidence_invalid') from error
    _require(root.tag == 'nico_native' and root.attrib == {'schema': HEADER_SCHEMA, 'file': source})
    _require([child.tag for child in root] == ['configuration', 'file_end'])
    footer = root.find('file_end')
    _require(footer.attrib.keys() == {'normal_return'} and not list(footer))
    normal_return = _boolean(footer.get('normal_return'))
    cfg = root.find('configuration')
    _require(set(cfg.attrib) == _CONFIGURATION_FIELDS)
    flags = {name: _boolean(cfg.get(name)) for name in _CONFIGURATION_FIELDS
             if name not in {'cfg', 'disposition'}}
    _require(len(cfg.get('cfg')) <= 16384 and cfg.get('disposition') in {
        'started_or_error', 'preprocess_only', 'empty_tokens_no_checks', 'configuration_only',
        'simplification_failed', 'duplicate_purged', 'checks_completed', 'checks_incomplete',
        'preprocess_error', 'terminated', 'internal_error'})
    children = [child.tag for child in cfg]
    _require(children and children[0] == 'effective' and children[-2:] == ['token_membership'] * 2
        and all(tag == 'include' for tag in children[1:-2]))
    effective = cfg.find('effective')
    _require(effective.attrib == {'std': standard}, 'worker_project_header_standard_mismatch')
    effective_values = {}
    for child in effective:
        _require(child.tag in {'define', 'undef', 'include_path', 'forced_input'}
            and set(child.attrib) == {'value'} and not list(child)
            and 0 < len(child.get('value')) <= 16384 and '\x00' not in child.get('value'))
        effective_values.setdefault(child.tag, []).append(child.get('value'))
    if effective_inputs is not None:
        _require(isinstance(effective_inputs,dict) and set(effective_inputs)=={'undef','include_path','forced_input'})
        _require(all(effective_values.get(key,[])==values for key,values in effective_inputs.items()),
            'worker_project_header_effective_inputs_mismatch')
    configured = {}
    for fragment in cfg.get('cfg').split(';') if cfg.get('cfg') else []:
        name, separator, value = fragment.partition('=')
        _require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\([^;]*\))?',name) is not None
            and name not in configured)
        configured[name] = value if separator else '1'
    observed = {}
    for fragment in effective_values.get('define',[]):
        name, separator, value = fragment.partition('=')
        if name in configured:
            parsed = value if separator else '1'
            _require(name not in observed or observed[name] == parsed)
            observed[name] = parsed
    _require(configured == observed, 'worker_project_header_configuration_mismatch')
    if configuration_defines is not None:
        _require(configured == configuration_defines, 'worker_project_header_configuration_mismatch')
    entered, unavailable = set(), []
    events = cfg.findall('include')
    _require(len(events) <= 4096)
    for event in events:
        _require(set(event.attrib) == {'file', 'parent', 'kind', 'entered'} and not list(event)
            and event.get('kind') in _KINDS)
        visited = _boolean(event.get('entered'))
        path, parent, kind = event.get('file'), event.get('parent'), event.get('kind')
        _require(0 < len(path) <= 4096 and len(parent) <= 4096)
        if visited:
            _require(kind in {'include', 'forced'} and path in locations
                and (parent == source or parent in entered or kind == 'forced' and parent == ''),
                'worker_project_header_location_unbound')
            entered.add(path)
        else:
            _require(kind not in {'include', 'forced'})
            if kind in {'missing', 'forced_not_loaded', 'depth_skipped'}:
                unavailable.append({'path': path, 'kind': kind})
    token_sets, stages_ok = [], True
    for stage, membership in zip(_STAGES, cfg.findall('token_membership')):
        _require(set(membership.attrib) == {'stage', 'captured', 'invalid', 'overflow'}
            and membership.get('stage') == stage)
        captured, invalid, overflow = (_boolean(membership.get(key)) for key in ('captured','invalid','overflow'))
        stages_ok &= captured and not invalid and not overflow
        names = []
        for child in membership:
            _require(child.tag == 'token_file' and set(child.attrib) == {'file'} and not list(child))
            names.append(child.get('file'))
        _require(len(names) <= 4096 and len(names) == len(set(names))
            and all(isinstance(name, str) and 0 < len(name) <= 4096 for name in names))
        token_sets.append(set(names))
    _require(token_sets[1] <= token_sets[0])
    _require(len(events)+sum(map(len,token_sets))<=4096)
    observed_bytes = sum(len(e.get('file').encode())+len(e.get('parent').encode())+len(e.get('kind').encode())+128 for e in events)
    observed_bytes += sum(len(name.encode())+128 for names in token_sets for name in names)
    _require(observed_bytes <= HEADER_LIMIT)
    physical_bound = not flags['token_logical_remap_observed']
    if physical_bound:
        _require(token_sets[0] <= entered | {source}, 'worker_project_header_location_unbound')
    complete = bool(normal_return and cfg.get('disposition') == 'checks_completed'
        and flags['checks_completed'] and flags['completed'] and flags['normal_pass_started']
        and flags['preprocessing_returned'] and not flags['preprocessing_had_output']
        and not flags['observation_overflow'] and stages_ok and not unavailable)
    if complete and effective_inputs is not None:
        _require(set(effective_inputs['forced_input']) <= entered,
            'worker_project_header_forced_input_unobserved')
    if flags['completed']:
        _require(flags['checks_completed'] and flags['normal_pass_started'] and stages_ok
            and cfg.get('disposition') == 'checks_completed' and flags['preprocessing_returned']
            and not flags['preprocessing_had_output'] and not flags['observation_overflow'] and not unavailable
            and token_sets[0] and token_sets[1], 'worker_project_header_false_completion')
    parsed = token_sets[1] if physical_bound and stages_ok else set()
    analyzed = parsed if complete else set()
    inventoried = sorted(locations)
    return {'schema': 'nico.cpp-header-context-evidence.v1',
        'native_trace_sha256': hashlib.sha256(raw).hexdigest(), 'source': source,
        'standard': standard, 'effective_inputs': effective_values,
        'inventoried_files': inventoried, 'include_observed_files': sorted(entered),
        'tokenized_files': sorted(token_sets[0]) if physical_bound and stages_ok else [],
        'parsed_token_files': sorted(parsed), 'normal_pass_token_files': sorted(analyzed),
        'unvisited_files': sorted(set(inventoried) - entered - {source}),
        'unavailable_inputs': unavailable, 'normal_pass_completed': complete,
        'physical_token_origin_verified': physical_bound and stages_ok,
        'line_or_branch_coverage_inferred': False, 'individual_checker_coverage_inferred': False,
        'limitations': ([] if physical_bound else ['logical_locations_remapped_physical_token_origin_unproven'])}
