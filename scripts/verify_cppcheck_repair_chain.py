"""Check patch application on a private copy before an expensive analyzer build.

Only mechanical identity/receipt checks are performed here. Native parser tests
and original-context qualification remain separate required evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from . import repair_cppcheck_format_var_template_ast as formatting
from . import repair_cppcheck_placement_ast as placement


def verify(source: Path) -> dict:
    raw, _ = placement._read(Path(source))
    # This fails closed unless the source is the pinned upstream tokenlist.cpp.
    expected_placement = placement.patched_bytes(raw)
    with tempfile.TemporaryDirectory(prefix='nico-repair-preflight-') as temporary:
        root = Path(temporary)
        target = root / 'lib' / 'tokenlist.cpp'
        target.parent.mkdir()
        target.write_bytes(raw)
        first = placement.apply_repair(target)
        if target.read_bytes() != expected_placement:
            raise ValueError('placement_output_mismatch')
        second = formatting.apply(root)
        expected_final = expected_placement.replace(formatting.OLD, formatting.NEW, 1)
        if target.read_bytes() != expected_final:
            raise ValueError('repair_output_mismatch')
        if first['source_after_sha256'] != second['source_before_sha256']:
            raise ValueError('repair_chain_mismatch')
        # Verify JSON serialization here as well as the emitted build records.
        json.loads(json.dumps([first, second], sort_keys=True))
    if placement._read(Path(source))[0] != raw:
        raise ValueError('preflight_source_changed')
    return {
        'schema': 'nico.cppcheck-repair-chain-preflight.v1',
        'upstream_commit': placement.UPSTREAM_COMMIT,
        'upstream_source_sha256': hashlib.sha256(raw).hexdigest(),
        'source_unchanged': True,
        'native_qualification_completed': False,
        'repairs': [first, second],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.source), sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
