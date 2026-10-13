"""Review-only, exact-source-bound specialization grouping overlay. No build/run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

UPSTREAM = 'ac9db3069b9f90e81e126a090b99ad456e122cf8'
SOURCE_HASHES = {
    'lib/templatesimplifier.cpp': '61e6d1c8be0327fe8689c132b95ad519d95685e88d9766e8862e625b80e11d4f',
    'lib/templatesimplifier.h': '92e8f21cca8a74e36fee87ce00f903ae76c35900bb04d6034ba2d90dc7dff0f6',
    'lib/token.cpp': 'f4e7b9234f1af3cd37dfd1b0dee6d17732c36abd830ae1c5200b118220795e1a',
}
BUILD_ANCHOR = b'        std::set<std::string> expandedtemplates;\n'
GROUP_BUILD = b'''        // Group stable declaration identities; keep original pointers and order.
        std::map<std::string, std::list<const Token *>> specializationsByName;
        for (const auto& declaration : mTemplateDeclarations) {
            if (!declaration.isAlias() && !declaration.isFriend())
                specializationsByName[declaration.fullName()].push_back(declaration.nameToken());
        }

'''
OLD_FILTER = b'''            // get specializations..
            std::list<const Token *> specializations;
            for (auto iter2 = mTemplateDeclarations.cbegin(); iter2 != mTemplateDeclarations.cend(); ++iter2) {
                if (iter2->isAlias() || iter2->isFriend())
                    continue;

                if (iter1->fullName() == iter2->fullName())
                    specializations.push_back(iter2->nameToken());
            }
'''
NEW_FILTER = b'''            const auto& specializations = specializationsByName.at(iter1->fullName());
'''
DELETE_ANCHOR = b'        for (auto it = mInstantiatedTemplates.cbegin(); it != mInstantiatedTemplates.cend(); ++it) {\n'
GROUP_CLEAR = b'''        // Do not retain non-owning groups across declaration/token deletion.
        specializationsByName.clear();

'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def transform(raw):
    if sha(raw) != SOURCE_HASHES['lib/templatesimplifier.cpp']:
        raise ValueError('specialization_groups_source_identity')
    for anchor in (BUILD_ANCHOR, OLD_FILTER, DELETE_ANCHOR):
        if raw.count(anchor) != 1:
            raise ValueError('specialization_groups_anchor_identity')
    return (raw.replace(BUILD_ANCHOR, GROUP_BUILD + BUILD_ANCHOR)
            .replace(OLD_FILTER, NEW_FILTER)
            .replace(DELETE_ANCHOR, GROUP_CLEAR + DELETE_ANCHOR))


def read_regular(path):
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError('specialization_groups_symlink')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024:
            raise ValueError('specialization_groups_source_type_or_size')
        raw = stream.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('specialization_groups_source_type_or_size')
    return raw


def create_overlay(source, output):
    source, output = source.absolute(), output.absolute()
    if output.resolve().is_relative_to(source.resolve()):
        raise ValueError('specialization_groups_output_inside_source')
    for parent in (output, *output.parents):
        if parent.is_symlink():
            raise ValueError('specialization_groups_symlink')
    inputs = {p: read_regular(source / p) for p in SOURCE_HASHES}
    if any(sha(inputs[p]) != h for p, h in SOURCE_HASHES.items()):
        raise ValueError('specialization_groups_source_identity')
    updated = transform(inputs['lib/templatesimplifier.cpp'])
    receipt = {'schema': 'nico.cppcheck-specialization-groups.v1', 'upstream': UPSTREAM,
               'input_sha256': dict(SOURCE_HASHES), 'output_sha256': sha(updated),
               'build_performed': False, 'analyzer_execution': False,
               'bitcoin_performance_claimed': False}
    output.mkdir()
    (output / 'lib').mkdir()
    (output / 'lib/templatesimplifier.cpp').write_bytes(updated)
    (output / 'receipt.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(create_overlay(args.source, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
