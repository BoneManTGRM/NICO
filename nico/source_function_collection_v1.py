"""Collection-only reconciliation; authenticity requires trusted persistence reload."""
from __future__ import annotations

from nico.source_function_measurements_v1 import KEY, _hash, _json, build_measurements, validate_measurements

KEY_COLLECTION = 'source_function_collection_v1'
VERSION = 'nico.source-function-collection.v1'


def collect_contract(source_files: dict, analyses: list, ast_result: dict, measurements: dict) -> dict:
    # Called while the complete parser records and acquired inputs still exist.
    # Rebuild from those records, not from summaries/top hotspots or supplied digests.
    expected = build_measurements(source_files, analyses, ast_result)
    if _json(expected) != _json(measurements):
        raise ValueError('collection_measurement_reconciliation_failed')
    return {'version': VERSION, 'identity': None,
            'inventory_sha256': expected['inventory_sha256'],
            'producer_source_sha256': expected['producer_source_sha256'],
            'measurement_sha256': _hash(_json(expected))}


def bind_collection(evidence: dict) -> None:
    contract = evidence.get(KEY_COLLECTION)
    measurement = evidence.get(KEY)
    if not isinstance(contract, dict) or not isinstance(measurement, dict) or measurement.get('identity') is None:
        evidence.pop(KEY_COLLECTION, None)
        return
    unbound = dict(measurement, identity=None)
    if (contract.get('version') != VERSION or contract.get('identity') is not None
            or contract.get('measurement_sha256') != _hash(_json(unbound))):
        evidence.pop(KEY_COLLECTION, None)
        return
    evidence[KEY_COLLECTION] = {**contract, 'identity': dict(measurement['identity']),
                               'measurement_sha256': _hash(_json(measurement))}


def validate_collection(evidence: dict) -> bool:
    contract, measurement = evidence.get(KEY_COLLECTION), evidence.get(KEY)
    if not isinstance(contract, dict) or not isinstance(measurement, dict):
        return False
    expected = {'version': VERSION, 'identity': measurement.get('identity'),
                'inventory_sha256': measurement.get('inventory_sha256'),
                'producer_source_sha256': measurement.get('producer_source_sha256'),
                'measurement_sha256': _hash(_json(measurement))}
    return (measurement.get('identity') is not None and _json(contract) == _json(expected)
            and validate_measurements(measurement, expected_identity=measurement['identity'],
                                      expected_inventory=measurement['inventory']))
