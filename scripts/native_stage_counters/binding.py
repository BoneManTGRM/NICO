"""Diagnostic-only runtime identity and actual analyzer environment boundary."""
from __future__ import annotations
import json
import re
from .instrument import SOURCE_SHA256, ORIGINAL_BINARY_SHA256
from . import specialization_groups as groups

OBSERVER_SHA256 = '45474684723784ea89d5531bf52730adedddc312814c083e990e8a2df1bf43f9'
ARCHIVE_SHA256 = 'dbf890120e44a7d0f99133d69f316c9e8d7dce0210f3ae627e248ffa1c4e7e92'
OVERLAY_SHA256 = 'a04d9852093ba90595cf71cdd5f6ad7698085edb1c6ed25cdca101f6ee516ff6'
HEADER_SHA256 = '2a3a4e2351e62b21d43f1922c6ea2c06a6f0145ca10ccbc05297745aa221d71c'
AFTER_SHA256 = {
    'lib/tokenize.cpp': '0ad11c73e55a130a3e9eb660b807353527f065d6eae58564546f00852d594c5e',
    'lib/templatesimplifier.cpp': '29ed29fd5a504ee6628927a7fabfe19f2b9ef8f80c4d5a518d93e4bc8ab44871',
}
FLAGS = ['--showtime=file', '--report-progress=1']
BUILD_FLAGS = ['MATCHCOMPILER=yes', 'FILESDIR=/opt/cppcheck', 'CXXFLAGS=-O2 -DNDEBUG', '-j2']


CANDIDATE_PATCH_SHA256 = 'f8d5989c168ef48f065fc262e7de42bf1611f71b740914608ca0ed6f7e98c14f'
GROUP_SCRIPT_SHA256 = '09cd155550eddb1518520bd875e314dd6cd08283c52c643ce303d523fa0011c8'
LOCAL_PRE_GROUPING_BINARY_SHA256 = 'ed79c96b90b246110b696290e580b555ffdc7438c6f6b878adc0bee48e9911c7'
LOCAL_UNINSTRUMENTED_BINARY_SHA256 = '3f1a95d83f380932d371e02430c1b36a0531be5a3c05eeee32bc0110b3451eaa'
PRE_GROUPING_BINARY_SHA256 = 'ce96e72d89e6801c1b2b3a27ec30a77434e943d1783112de93b3881f27d8ab68'


def expected_grouping():
    return {'schema': 'nico.cppcheck-specialization-groups.v1', 'upstream': groups.UPSTREAM,
            'input_sha256': dict(groups.SOURCE_HASHES),
            'output_sha256': SOURCE_SHA256['lib/templatesimplifier.cpp'],
            'build_performed': False, 'analyzer_execution': False,
            'bitcoin_performance_claimed': False}


def validate_grouping(value):
    if value != expected_grouping():
        raise ValueError('diagnostic_grouping_receipt_identity')
    return value


def validate_overlay(value):
    expected_members = [{'path': p, 'before_sha256': SOURCE_SHA256[p],
                         'after_sha256': AFTER_SHA256[p], 'semantic_bytes_restored': True}
                        for p in sorted(SOURCE_SHA256)]
    if (not isinstance(value, dict) or value.get('schema') != 'nico.cppcheck-stage-counter-overlay.v1'
            or value.get('upstream_commit') != 'ac9db3069b9f90e81e126a090b99ad456e122cf8'
            or value.get('overlay_identity_sha256') != OVERLAY_SHA256
            or value.get('header_sha256') != HEADER_SHA256 or value.get('members') != expected_members
            or value.get('original_binary_sha256') != ORIGINAL_BINARY_SHA256
            or value.get('instrumented_binary_sha256') is not None
            or value.get('instrumentation_only') is not True
            or value.get('build_performed') is not False
            or value.get('binary_equivalence_claimed') is not False
            or value.get('activation') != {'environment': 'NICO_CPP_STAGE_COUNTERS', 'exact_value': '1'}):
        raise ValueError('diagnostic_stage_overlay_binding')
    return value


def binding_digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_binding(value, image, expected_sha256, original_image):
    if not isinstance(value, dict):
        raise ValueError('diagnostic_stage_runtime_binding')
    from pathlib import Path
    from .build import recipe_identity
    _, expected_recipe = recipe_identity(Path('docker/assessment-full-project-fuzz.Dockerfile'))
    if (not isinstance(expected_sha256,str) or not re.fullmatch(r'[a-f0-9]{64}',expected_sha256)
            or binding_digest(value)!=expected_sha256 or value.get('recipe')!=expected_recipe
            or value.get('original_image')!=original_image):
        raise ValueError('diagnostic_stage_provenance_binding')
    binary = value.get('instrumented_binary_sha256', '')
    if (value.get('schema') != 'nico.stage-runtime-binding.v4'
            or type(value.get('record_version')) is not int or value.get('record_version') != 3
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', image)
            or value.get('image') != image or value.get('original_image') == image
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', value.get('original_image', ''))
            or not re.fullmatch(r'[a-f0-9]{64}', binary)
            or binary in (ORIGINAL_BINARY_SHA256, PRE_GROUPING_BINARY_SHA256, LOCAL_UNINSTRUMENTED_BINARY_SHA256, LOCAL_PRE_GROUPING_BINARY_SHA256)
            or value.get('original_binary_sha256') != ORIGINAL_BINARY_SHA256
            or value.get('observer_sha256') != OBSERVER_SHA256
            or value.get('original_archive_sha256') != ARCHIVE_SHA256
            or value.get('flags') != FLAGS or value.get('build_flags') != BUILD_FLAGS
            or value.get('compiler_version') != '14.2.0'
            or value.get('activation') != {'environment': 'NICO_CPP_STAGE_COUNTERS', 'exact_value': '1'}
            or value.get('build_verified') is not True):
        raise ValueError('diagnostic_stage_runtime_binding')
    validate_grouping(value.get('grouping'))
    if (value.get('candidate_patch_sha256') != CANDIDATE_PATCH_SHA256
            or value.get('candidate_source_sha256') != AFTER_SHA256):
        raise ValueError('diagnostic_candidate_source_binding')
    validate_overlay(value.get('overlay'))
    return value


def analyzer_environment(argv, environment, enabled, allowed_commands):
    """No ambient inheritance: this runs inside the diagnostic collector wrapper."""
    if type(enabled) is not bool:
        raise ValueError('diagnostic_stage_flag_invalid')
    result = dict(environment)
    if 'NICO_CPP_STAGE_COUNTERS' in result:
        raise ValueError('diagnostic_stage_ambient_key')
    if not enabled:
        return result
    if argv == ['/usr/local/bin/cppcheck', '--version']:
        return result
    if argv not in allowed_commands or not argv or argv[0] != '/usr/local/bin/cppcheck':
        raise ValueError('diagnostic_stage_command_invalid')
    result['NICO_CPP_STAGE_COUNTERS'] = '1'
    return result


def load_binding(path, image, expected_sha256, original_image):
    from .instrument import read_regular
    raw = read_regular(path.absolute())
    if len(raw) > 65536:
        raise ValueError('diagnostic_stage_binding_size')
    def unique(pairs):
        value = {}
        for k, v in pairs:
            if k in value: raise ValueError('diagnostic_stage_duplicate_key')
            value[k] = v
        return value
    return validate_binding(json.loads(raw, object_pairs_hook=unique), image, expected_sha256, original_image)
