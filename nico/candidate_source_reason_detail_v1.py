"""Closed, evidence-bound diagnostics; never a disposition or inferred budget cause."""
from collections.abc import Mapping
import hashlib

VERSION = 'nico.candidate-source-availability-detail.v1'
CAPTURE_LABELS = {
    'capture_deadline': ('Capture reached its deadline at this path', 'La captura alcanzó su plazo en esta ruta'),
    'inventory_missing_or_unsupported': ('Path absent from supported regular-file inventory', 'La ruta no figura en el inventario de archivos regulares compatibles'),
    'file_size_limit': ('Source exceeded the per-file capture limit', 'El código superó el límite de captura por archivo'),
    'input_size_limit': ('Source exceeded the remaining aggregate input allowance', 'El código superó el límite restante de entrada total'),
    'inventory_entry_invalid': ('Retained capture rejected an invalid inventory entry', 'La captura rechazó una entrada de inventario inválida'),
    'blob_integrity_unavailable': ('Captured blob bytes did not pass identity validation', 'Los bytes capturados no superaron la validación de identidad'),
    'observation_output_limit': ('Observation exceeded remaining retained output allowance', 'La observación superó el límite restante de salida conservada'),
    'capture_operation_failed': ('Capture operation failed at this path; cause unspecified', 'La operación de captura falló en esta ruta; causa sin especificar'),
}
LABELS = {
    **CAPTURE_LABELS,
    'source_not_retained': ('No observation retained for this candidate path; cause unknown', 'No se conservó una observación para esta ruta; causa desconocida'),
    'capture_observations_invalid': ('Retained observation collection is unavailable or malformed', 'La colección de observaciones conservadas no está disponible o es inválida'),
    'candidate_path_unusable': ('Candidate path cannot be safely matched', 'La ruta del candidato no se puede vincular de forma segura'),
    'observation_parse_unavailable': ('Retained observation reports parsing unavailable', 'La observación conservada informa que el análisis sintáctico no está disponible'),
    'observation_size_limit': ('Retained observation reports a source size limit', 'La observación conservada informa un límite de tamaño del código'),
    'observation_binding_invalid': ('Retained observation reports invalid source binding', 'La observación conservada informa una vinculación del código inválida'),
    'observation_scope_conflict': ('Retained observation binding conflicts with the expected source', 'La vinculación de la observación conservada contradice el código esperado'),
    'observation_status_unknown': ('Retained observation status is missing or unsupported', 'El estado de la observación conservada falta o no es compatible'),
    'not_recorded': ('Source availability detail was not retained', 'No se conservó el detalle de disponibilidad del código'),
}

def path_digest(path):
    try:
        return hashlib.sha256(path.encode('utf-8')).hexdigest()
    except (AttributeError, UnicodeError):
        return None


def capture_detail(observations, path, scope, outcomes=None):
    """Caller must first validate capture scope and the candidate identity."""
    if not isinstance(observations, Mapping):
        code = 'capture_observations_invalid'
    elif path is None:
        code = 'candidate_path_unusable'
    elif path not in observations:
        code = 'source_not_retained'
        if isinstance(outcomes, Mapping) and outcomes.get('artifact_schema') == 'nico.candidate-path-capture-outcomes.v1':
            entries = outcomes.get('path_sha256_reasons')
            digest = path_digest(path)
            value = entries.get(digest) if digest is not None and isinstance(entries, Mapping) else None
            if isinstance(value, str) and value in CAPTURE_LABELS:
                code = value
    else:
        observation = observations[path]
        binding = observation.get('source_binding') if isinstance(observation, Mapping) else None
        if binding is not None and (not isinstance(binding, Mapping) or any(
                binding.get(key) != expected for key, expected in (
                    ('repository', scope['repository']), ('commit_sha', scope['commit_sha']), ('path', path)))):
            code = 'observation_scope_conflict'
        else:
            status = observation.get('status') if isinstance(observation, Mapping) else None
            code = {'source_parse_unavailable': 'observation_parse_unavailable',
                    'source_size_limit': 'observation_size_limit',
                    'source_binding_invalid': 'observation_binding_invalid'}.get(status, 'observation_status_unknown') if isinstance(status, str) else 'observation_status_unknown'
    return {'artifact_schema': VERSION, 'code': code}

def packet_detail(packet):
    value = packet.get('source_availability_detail')
    code = value.get('code') if isinstance(value, Mapping) and value.get('artifact_schema') == VERSION else None
    return code if isinstance(code, str) and code in LABELS else 'not_recorded'
