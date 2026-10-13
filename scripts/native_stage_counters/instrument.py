"""Create a review-only, source-pinned Cppcheck instrumentation overlay.

Never builds, runs, downloads, edits the input tree, or enables a workflow.
Apply this overlay only to a separate trusted-tool build copy after review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

SOURCE_SHA256 = {
    'lib/tokenize.cpp': '76beaa920046dbe057c5b20b09c043802351692657e2b3f269cf4612984eac88',
    'lib/templatesimplifier.cpp': 'd77673074aa057005844006f6a8e7a97a3320155c2e538635463e2ab82028d13',
}
ORIGINAL_BINARY_SHA256 = 'f5215eabbc2666859254ace73a5f53eb991cb285f94a733d6682ea85f26d2544'
HEADER = Path(__file__).with_name('nico_stage_counters.h')
LIMIT = 2 * 1024 * 1024
BEGIN = b'/* NICO_STAGE_INSERT_BEGIN */\n'
END = b'/* NICO_STAGE_INSERT_END */\n'


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def insert(raw: bytes, anchor: bytes, statement: bytes, count: int = 1) -> bytes:
    if raw.count(anchor) != count:
        raise ValueError('stage_anchor_mismatch')
    return raw.replace(anchor, anchor + BEGIN + statement + b'\n' + END)


def strip_instrumentation(raw: bytes) -> bytes:
    """Independent byte restoration check: semantic source stays exactly intact."""
    while BEGIN in raw:
        start = raw.index(BEGIN)
        end = raw.index(END, start) + len(END)
        raw = raw[:start] + raw[end:]
    return raw


def instrument(relative: str, raw: bytes) -> bytes:
    if relative not in SOURCE_SHA256 or digest(raw) != SOURCE_SHA256[relative]:
        raise ValueError('stage_source_identity_mismatch')
    original = raw
    if relative == 'lib/tokenize.cpp':
        raw = insert(raw, b'#include "tokenize.h"\n', b'#include "nico_stage_counters.h"')
        raw = insert(raw, b'bool Tokenizer::simplifyUsing()\n{\n',
                     b'    NicoStage::Frame nicoUsing(2);')
        raw = insert(raw, b'    // simplify using N::x; to using x = N::x;\n'
                     b'    for (Token* tok = list.front(); tok; tok = tok->next()) {\n',
                     b'        NicoStage::bump(NicoStage::PreludeVisits);')
        raw = insert(raw, b'    std::list<Using> usingList;\n\n    for (Token *tok = list.front(); tok; tok = tok->next()) {\n',
                     b'        NicoStage::bump(NicoStage::OuterVisits);')
        raw = insert(raw, b'        std::string scope1 = currentScope1->fullName;\n',
                     b'        NicoStage::Frame nicoAlias(3);')
        raw = insert(raw, b'        for (Token* tok1 = startToken; !skip && tok1 && tok1 != endToken; tok1 = tok1->next()) {\n',
                     b'            NicoStage::bump(NicoStage::InnerVisits);')
        raw = insert(raw, b'            children.emplace_back(this, scopeType, scopeName, bodyStartToken, bodyEndToken);\n',
                     b'            NicoStage::bump(NicoStage::ScopeNodes);')
        raw = insert(raw, b'        const ScopeInfo3 * findScope(const std::string & scope) const {\n',
                     b'            NicoStage::bump(NicoStage::ScopeQueries);')
        raw = insert(raw, b'        const ScopeInfo3 * findInChildren(const std::string & scope) const {\n',
                     b'            NicoStage::bump(NicoStage::ChildVisits);')
        raw = insert(raw, b'        bool findTypeInBase(const std::string &scope) const {\n',
                     b'            NicoStage::bump(NicoStage::BaseVisits);')
        raw = insert(raw, b'        const ScopeInfo3 *memberClassScope)\n    {\n',
                     b'        NicoStage::bump(NicoStage::MatchCalls);')
        raw = insert(raw, b'            for (const ScopeInfo3* parent = scopeInfo; parent; parent = parent->parent) {\n',
                     b'                NicoStage::bump(NicoStage::BaseQueries);')
        # Restrict repeated assignment anchors to the pinned simplifyUsing function.
        first = raw.index(b'bool Tokenizer::simplifyUsing()\n')
        last = raw.index(b'void Tokenizer::simplifyUsingError(', first)
        body = raw[first:last]
        anchor = b'            const auto nReplace = tokDistance(start, usingEnd);\n'
        if body.count(anchor) != 1:
            raise ValueError('stage_anchor_mismatch')
        body = body.replace(anchor, BEGIN + b'            NicoStage::bump(NicoStage::RhsDistanceCalls);\n' + END + anchor)
        body = insert(body, anchor, b'            NicoStage::distanceTokens(static_cast<std::uint64_t>(nReplace));')
        body = insert(body, b'            Token *type = start;\n',
                      b'            NicoStage::bump(NicoStage::RhsParses);')
        body = insert(body, b'                    substitute = true;\n',
                      b'                    NicoStage::bump(NicoStage::Replacements);', 2)
        raw = raw[:first] + body + raw[last:]
    else:
        raw = insert(raw, b'#include "templatesimplifier.h"\n', b'#include "nico_stage_counters.h"')
        raw = insert(raw, b'    for (; passCount < passCountMax; ++passCount) {\n',
                     b'        NicoStage::Frame nicoTemplate(1, passCount + 1);')
        raw = insert(raw, b'            if (instantiated) {\n', b'                NicoStage::instantiated();')
    if strip_instrumentation(raw) != original:
        raise ValueError('stage_semantic_source_changed')
    return raw


def read_regular(path: Path) -> bytes:
    if path.parent != path.parent.resolve(strict=True):
        raise ValueError('stage_symlink_parent')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise ValueError('stage_source_type_or_size')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(LIMIT + 1)
        if len(raw) != info.st_size:
            raise ValueError('stage_source_changed_during_read')
        return raw
    finally:
        os.close(fd)


def create_overlay(source: Path, destination: Path) -> dict:
    source = source.absolute()
    destination = destination.absolute()
    if source != source.resolve(strict=True):
        raise ValueError('stage_symlink_source')
    if destination == source or source in destination.parents:
        raise ValueError('stage_output_must_be_outside_source')
    if destination.parent != destination.parent.resolve(strict=True):
        raise ValueError('stage_symlink_destination')
    # Validate everything before creating output. Original bytes never overwritten.
    originals = {name: read_regular(source / name) for name in SOURCE_SHA256}
    patched = {name: instrument(name, raw) for name, raw in originals.items()}
    header = read_regular(HEADER.absolute())
    receipt = {
        'schema': 'nico.cppcheck-stage-counter-overlay.v1',
        'upstream_commit': 'ac9db3069b9f90e81e126a090b99ad456e122cf8',
        'instrumentation_only': True,
        'original_binary_sha256': ORIGINAL_BINARY_SHA256,
        'instrumented_binary_sha256': None,
        'instrumented_binary_requires_new_identity': True,
        'build_performed': False, 'assessed_execution_performed': False,
        'binary_equivalence_claimed': False,
        'activation': {'environment': 'NICO_CPP_STAGE_COUNTERS', 'exact_value': '1'},
        'members': [{'path': n, 'before_sha256': digest(originals[n]),
                     'after_sha256': digest(patched[n]), 'semantic_bytes_restored': True}
                    for n in sorted(patched)],
        'header_sha256': digest(header),
    }
    identity = {'sources': {n: digest(v) for n, v in patched.items()}, 'header_sha256': digest(header)}
    receipt['overlay_identity_sha256'] = digest(json.dumps(identity, sort_keys=True).encode())
    destination.mkdir()  # Exclusive: no clobber, merge, or retry on existing destination.
    (destination / 'lib').mkdir()
    for name, raw in patched.items():
        (destination / name).write_bytes(raw)
    (destination / 'lib/nico_stage_counters.h').write_bytes(header)
    (destination / 'stage-counter-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(create_overlay(args.source, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
