"""Diagnostic-only runtime identity and actual analyzer environment boundary."""
from __future__ import annotations
import json
import re
from .instrument import SOURCE_SHA256, ORIGINAL_BINARY_SHA256

OBSERVER_SHA256 = '45474684723784ea89d5531bf52730adedddc312814c083e990e8a2df1bf43f9'
ARCHIVE_SHA256 = 'dbf890120e44a7d0f99133d69f316c9e8d7dce0210f3ae627e248ffa1c4e7e92'
OVERLAY_SHA256 = '4c82ebc973709634ad378c98ce0fd0c7fdfe4a73726b48503967de3c60319607'
HEADER_SHA256 = '924d2ad1ffd460fb894df6b493be029db2c1dd8b5b335f58bcdcbf69377f693f'
AFTER_SHA256 = {
    'lib/tokenize.cpp': '0ad11c73e55a130a3e9eb660b807353527f065d6eae58564546f00852d594c5e',
    'lib/templatesimplifier.cpp': 'ecbcb62e14104ad396d7b41bfcddb006556c3da850a0e8e9240ec6e5235d45c2',
}
FLAGS = ['--showtime=file', '--report-progress=1']
BUILD_FLAGS = ['MATCHCOMPILER=yes', 'FILESDIR=/opt/cppcheck', 'CXXFLAGS=-O2 -DNDEBUG', '-j2']


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
    if (value.get('schema') != 'nico.stage-runtime-binding.v1'
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', image)
            or value.get('image') != image or value.get('original_image') == image
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', value.get('original_image', ''))
            or not re.fullmatch(r'[a-f0-9]{64}', binary) or binary == ORIGINAL_BINARY_SHA256
            or value.get('original_binary_sha256') != ORIGINAL_BINARY_SHA256
            or value.get('observer_sha256') != OBSERVER_SHA256
            or value.get('original_archive_sha256') != ARCHIVE_SHA256
            or value.get('flags') != FLAGS or value.get('build_flags') != BUILD_FLAGS
            or value.get('compiler_version') != '14.2.0'
            or value.get('activation') != {'environment': 'NICO_CPP_STAGE_COUNTERS', 'exact_value': '1'}
            or value.get('build_verified') is not True):
        raise ValueError('diagnostic_stage_runtime_binding')
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
