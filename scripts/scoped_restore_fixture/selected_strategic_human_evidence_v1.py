"""Static source-pinned selected definitions; checked by verifier before import."""
import json
import hashlib
from typing import Any
from collections.abc import Mapping
from nico.report_delivery_timing_v1 import report_delivery_phase
from selected_decision_grade_human_evidence_v1 import MODULE_DEFINITIONS
VERSION = 'nico.strategic_human_evidence.v2'
MODULES: dict[str, dict[str, Any]] = {str(definition['module_id']): {'label': str(definition['label']), 'description': str(definition['description']), 'required_fields': tuple((str(item) for item in definition['required_fields']))} for definition in MODULE_DEFINITIONS}

def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

def verify_strategic_human_evidence(value: Any) -> bool:
    """Verify the top-level package and every embedded module digest after storage."""
    if not isinstance(value, Mapping):
        return False
    source = dict(value)
    claimed = str(source.pop('human_evidence_sha256', '') or '')
    if not claimed or claimed != _canonical_hash(source):
        return False
    modules = source.get('modules')
    if not isinstance(modules, Mapping) or set(modules) != set(MODULES):
        return False
    for module_id, raw in modules.items():
        if not isinstance(raw, Mapping) or str(raw.get('module_id') or '') != str(module_id):
            return False
        module = dict(raw)
        module_claimed = str(module.pop('module_sha256', '') or '')
        if not module_claimed or module_claimed != _canonical_hash(module):
            return False
    return True
