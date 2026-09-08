"""Retain complete checkout input evidence before dependency preparation.

An ESLint target proves JavaScript/TypeScript syntax exists. It does not prove
that npm dependency auditing or TypeScript project compilation has inputs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

VERSION = 'nico.node-scanner-input-inventory.v1'
SCOPE = 'complete_checkout_before_dependency_preparation'
NODE_DEPENDENCY_NAMES = frozenset({
    'package.json', 'package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock',
    'pnpm-lock.yaml', 'bun.lock', 'bun.lockb', 'deno.json', 'deno.jsonc', 'deno.lock',
})
_SHA = re.compile(r'[0-9a-f]{40}\Z')
_TS_COMMAND = re.compile(r'(?<![\w-])(?:tsc|ts-node|tsx)(?![\w-])')
REASONS = {
    'npm-audit': 'The complete assessed checkout contains no JavaScript dependency manifest or lockfile; npm-audit is not applicable. Standalone JavaScript remains in ESLint scope.',
    'typescript': 'The complete assessed checkout contains no TypeScript source, configuration, or declared compiler input; TypeScript compilation is not applicable. JavaScript remains in ESLint scope.',
}


def inventory_digest(inventory: Mapping[str, Any]) -> str:
    value = {key: item for key, item in inventory.items() if key != 'inventory_sha256'}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def inspect_node_inputs(repo: Path, commit_sha: str, *, max_entries: int = 100_000) -> dict[str, Any]:
    paths: list[str] = []
    dependencies: list[str] = []
    typescript: list[str] = []
    manifests: list[dict[str, str]] = []
    errors: list[str] = []
    root = repo.resolve()
    if not root.is_dir() or not _SHA.fullmatch(commit_sha) or max_entries < 1:
        errors.append('exact_checkout_identity_unavailable')

    def unreadable(_: OSError) -> None:
        errors.append('checkout_directory_unreadable')

    for current, directories, files in os.walk(root, followlinks=False, onerror=unreadable):
        directories[:] = sorted(name for name in directories if name != '.git')
        for name in [*directories, *sorted(files)]:
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            if relative == '.git':
                continue
            paths.append(relative)
            if len(paths) > max_entries:
                errors.append('checkout_inventory_limit_exceeded')
                break
            if path.is_symlink():
                errors.append('checkout_symlink_not_inspected')
                continue
            lower = name.casefold()
            if lower in NODE_DEPENDENCY_NAMES:
                dependencies.append(relative)
            if lower.endswith(('.ts', '.tsx', '.mts', '.cts')) or (
                lower.startswith(('tsconfig', 'jsconfig')) and lower.endswith('.json')
            ):
                typescript.append(relative)
            if lower == 'package.json':
                try:
                    if path.stat().st_size > 1_048_576:
                        raise ValueError('manifest exceeds limit')
                    raw = path.read_bytes()
                    package = json.loads(raw)
                    if not isinstance(package, dict):
                        raise ValueError('invalid package object')
                    manifests.append({'path': relative, 'sha256': hashlib.sha256(raw).hexdigest()})
                    if any(key in package and not isinstance(package[key], dict) for key in (
                        'dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'
                    )):
                        raise ValueError('invalid dependency declaration')
                    declared = any(
                        isinstance(package.get(key), dict) and 'typescript' in package[key]
                        for key in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies')
                    )
                    scripts = package.get('scripts') or {}
                    if not isinstance(scripts, dict):
                        raise ValueError('invalid scripts object')
                    if declared or package.get('types') or package.get('typings') or any(
                        isinstance(command, str) and _TS_COMMAND.search(command)
                        for command in scripts.values()
                    ):
                        typescript.append(relative)
                except (OSError, ValueError, UnicodeError):
                    errors.append('package_manifest_not_completely_inspected')
        if len(paths) > max_entries:
            break
    inventory: dict[str, Any] = {
        'schema': VERSION, 'scope': SCOPE, 'commit_sha': commit_sha,
        'inventory_complete': not errors, 'inspected_path_count': len(paths),
        'inspected_paths_sha256': hashlib.sha256(json.dumps(sorted(paths), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(),
        'node_dependency_paths': sorted(set(dependencies)),
        'typescript_input_paths': sorted(set(typescript)),
        'package_manifests': sorted(manifests, key=lambda item: item['path']),
        'errors': sorted(set(errors)),
        'submodule_content_scope': 'only_content_present_in_the_assessed_checkout',
    }
    inventory['inventory_sha256'] = inventory_digest(inventory)
    return inventory


def justified_inapplicability(value: Any, scanner: str, expected_commit: str) -> bool:
    if not isinstance(value, Mapping) or scanner not in REASONS:
        return False
    if (
        value.get('schema') != VERSION or value.get('scope') != SCOPE
        or not _SHA.fullmatch(str(expected_commit)) or value.get('commit_sha') != expected_commit
        or value.get('inventory_complete') is not True or value.get('errors') != []
        or type(value.get('inspected_path_count')) is not int
        or value['inspected_path_count'] < 0
        or not re.fullmatch(r'[0-9a-f]{64}', str(value.get('inspected_paths_sha256') or ''))
        or value.get('inventory_sha256') != inventory_digest(value)
    ):
        return False
    field = 'node_dependency_paths' if scanner == 'npm-audit' else 'typescript_input_paths'
    return value.get(field) == []


def observation_bytes(inventory: Mapping[str, Any], scanner: str) -> bytes:
    return json.dumps({
        'schema': 'nico.node-applicability-observation.v1', 'scanner': scanner,
        'execution_observed': False, 'inventory': inventory,
    }, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
