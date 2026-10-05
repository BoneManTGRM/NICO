"""Full-project collection handoff; target failures never become passing tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from nico.assessment_cpp_collection import validate_project_collection
from nico.assessment_cpp_project_snapshot import _stable_bytes, PROJECT_GENERATED_STREAM_LIMIT
from scripts.export_qualified_cpp_worker_image import _canonical, export_qualified_image

CONTRACTS = ('bitcoin-configuration-benchmark.json', 'bitcoin-baseline-execution.json',
             'bitcoin-runtime-scope.json')


def validate_collection(directory, *, source_sha, image, retain=None, enabled_targets_required=True):
    """Require current-policy evidence; False permits historical reads only.

    Export and promotion always use the strict default. A legacy receipt from
    the same producer/image must not satisfy the new release's required scope.
    """
    root = Path(directory).absolute()
    def read(name, limit):
        raw = _stable_bytes(root, name, limit)
        if retain is not None:
            destination = Path(retain) / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if destination.read_bytes() != raw:
                    raise ValueError('image_collection_duplicate_mismatch')
            else:
                with destination.open('xb') as output:
                    output.write(raw)
        return raw
    receipt = json.loads(read('receipt.json', 16 * 1024 * 1024))
    contracts = [read(name, 16384) for name in CONTRACTS]
    decision = validate_project_collection(receipt,
        lambda ref: read(ref['path'], PROJECT_GENERATED_STREAM_LIMIT),
        manifest_raw=contracts[0], baseline_raw=contracts[1], scope_raw=contracts[2],
        producer_source_sha=source_sha, image=image,
        enabled_targets_required=enabled_targets_required)
    if json.loads(read('collection-acceptance.json', 16 * 1024 * 1024)) != decision:
        raise ValueError('image_collection_decision_mismatch')
    return hashlib.sha256(_canonical(decision)).hexdigest()


def export(directory, proof, metadata, recipe, output, *, source_sha, **kwargs):
    """Export once, binding same-image controls and revalidated native collection."""
    image = metadata[0]['Id']
    collection_hash = validate_collection(directory, source_sha=source_sha, image=image)
    result = export_qualified_image(proof, metadata, recipe, output, source_sha=source_sha, **kwargs)
    try:
        retained_hash = validate_collection(directory, source_sha=source_sha, image=image,
                                             retain=Path(output) / 'collection')
        if retained_hash != collection_hash:
            raise ValueError('image_collection_changed')
        result.update(schema='nico.qualified-image-handoff.v3',
            full_project_collection_sha256=collection_hash,
            scope='same-image owned controls and complete full-project collection; target findings retained; activation separate')
        (Path(output) / 'handoff.json').write_bytes(_canonical(result) + b'\n')
        return result
    except BaseException:
        shutil.rmtree(output)
        raise
