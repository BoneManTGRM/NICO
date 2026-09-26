"""Data-only application of prospective collection policy to a retained v1 run.

The caller supplies independently verified GitHub provenance. A prospective copy
is labelled v2 only in memory. This does not amend or upgrade the original run.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY))
from nico.assessment_cpp_collection import validate_project_collection
from nico.assessment_cpp_project_snapshot import _stable_bytes, PROJECT_GENERATED_STREAM_LIMIT
from nico.assessment_worker_receipts import canonical_bytes

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--artifact-directory', type=Path, required=True)
parser.add_argument('--producer-source-sha', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
original_bytes = _stable_bytes(args.artifact_directory, 'receipt.json', 16*1024*1024)
original = json.loads(original_bytes)
assert original['schema'] == 'nico.cpp-configuration-qualification.v1'
prospective = deepcopy(original)
prospective.update(schema='nico.cpp-configuration-qualification.v2', producer_source_sha=args.producer_source_sha)
fixtures = REPOSITORY / 'tests/fixtures/cpp'
decision = validate_project_collection(prospective,
    lambda ref: _stable_bytes(args.artifact_directory, ref['path'], PROJECT_GENERATED_STREAM_LIMIT),
    manifest_raw=(fixtures/'bitcoin-configuration-benchmark.json').read_bytes(),
    baseline_raw=(fixtures/'bitcoin-baseline-execution.json').read_bytes(),
    scope_raw=(fixtures/'bitcoin-runtime-scope.json').read_bytes(),
    producer_source_sha=args.producer_source_sha, image=original['probe']['image_config_digest'])
assert decision['runtime']['summary'] == original['probe']['runtime_summary']
assert _stable_bytes(args.artifact_directory, 'receipt.json', 16*1024*1024) == original_bytes
result = {
    'new_native_execution': False,
    'historical_receipt_unchanged': True,
    'historical_receipt_sha256': hashlib.sha256(original_bytes).hexdigest(),
    'historical_receipt_schema': original['schema'],
    'provenance': 'Caller-supplied verified GitHub revision; v2 copy is prospective, not a historical v2 receipt.',
    'decision_sha256': hashlib.sha256(canonical_bytes(decision)).hexdigest(),
    'collection_complete': decision['collection_complete'],
    'target_tests_passed': decision['target_tests_passed'],
    'baseline_passed': len(decision['baseline']['passed']),
    'compiler_contexts': decision['compiler_contexts'], 'static_contexts': decision['static_contexts'],
    'runtime_summary_unchanged': True,
    'runtime_artifact_sha256': decision['runtime']['runtime_artifact_sha256'],
    'runtime_summary_sha256': decision['runtime']['runtime_summary_sha256'],
    'full_project_qualified': False, 'production_qualified': False,
}
args.output.write_bytes(canonical_bytes(result) + b'\n')
print(json.dumps(result, indent=2))
