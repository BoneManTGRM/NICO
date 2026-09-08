"""Bounded, conservative evidence for a native OSV no-package result.

This inventory is only used after OSV reports exit 128. It cannot turn a tool
failure, ignored manifest, unsupported dependency file, or unreadable tree clean.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Includes package declarations as well as supported lockfiles. An unsupported
# declaration means coverage is missing, not that dependency analysis is N/A.
_NAMES = frozenset({
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
    "pnpm-lock.yaml", "bun.lock", "bun.lockb", "deno.json", "deno.jsonc", "deno.lock",
    "pyproject.toml", "poetry.lock", "pipfile", "pipfile.lock", "uv.lock",
    "pdm.lock", "setup.py", "setup.cfg", "environment.yml", "environment.yaml",
    "go.mod", "go.sum", "go.work", "cargo.toml", "cargo.lock", "gemfile",
    "gemfile.lock", "gems.rb", "gems.locked", "composer.json", "composer.lock",
    "pom.xml", "build.gradle", "build.gradle.kts", "gradle.lockfile",
    "packages.lock.json", "packages.config", "project.json", "project.assets.json",
    "directory.packages.props", "nuget.config", "pubspec.yaml", "pubspec.lock",
    "mix.exs", "mix.lock", "package.swift", "package.resolved", "podfile",
    "podfile.lock", "cartfile", "cartfile.resolved", "conanfile.txt", "conanfile.py",
    "conan.lock", "vcpkg.json", "vcpkg-configuration.json", "renv.lock",
    "description", "pak.lock", "requirements.in", "requirements.txt",
    "osv-scanner.toml", "sbom.json", "bom.json", "bom.xml", "sbom.xml",
    "manifest.json", "project.clj", "deps.edn", "build.sbt", "rebar.config",
    "rebar.lock", "cpanfile", "cpanfile.snapshot", "cpan.meta", "meta.json",
    "meta.yml", "build.zig.zon", "lakefile.toml", "lake-manifest.json",
    "cabal.project", "cabal.project.freeze", "stack.yaml", "stack.yaml.lock",
})
_PATTERNS = ("requirements*.txt", "requirements*.in", "*.csproj", "*.fsproj",
             "*.vbproj", "*.gemspec", "*.cabal", "*.spdx", "*.spdx.json",
             "*.cdx.json", "*.cdx.xml", "*.lock", "*.lock.json")


VERSION = 'nico.osv-package-inventory.v2'
SCOPE = 'complete_checkout_before_dependency_preparation'


def inventory_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps({key: item for key, item in value.items() if key != 'inventory_sha256'},
                                    sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def justified_no_packages(value: Any, expected_commit: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    paths = value.get('inspected_paths')
    return (value.get('schema') == VERSION and value.get('scope') == SCOPE
            and bool(re.fullmatch(r'[0-9a-f]{40}', expected_commit))
            and value.get('commit_sha') == expected_commit
            and value.get('inventory_complete') is True and value.get('errors') == []
            and value.get('no_declared_package_sources') is True
            and value.get('package_source_paths') == []
            and isinstance(paths, list) and all(isinstance(path, str) and path for path in paths)
            and len(paths) == len(set(paths)) and value.get('inspected_path_count') == len(paths)
            and value.get('inventory_sha256') == inventory_digest(value))


def inspect_package_sources(repo: Path, commit_sha: str = '', *, max_entries: int = 100_000) -> dict[str, Any]:
    """Inspect all snapshot paths except Git internals; never follow symlinks."""
    hints: list[str] = []
    paths: list[str] = []
    errors: list[str] = []
    root = repo.resolve()
    if not root.is_dir() or max_entries < 1:
        errors.append("snapshot_directory_unavailable")
    def walk_error(_: OSError) -> None:
        errors.append("snapshot_directory_unreadable")
    for current, directories, files in os.walk(root, followlinks=False, onerror=walk_error):
        directories[:] = sorted(name for name in directories if name != ".git")
        for name in [*directories, *sorted(files)]:
            item = Path(current) / name
            relative = item.relative_to(root).as_posix()
            if relative == ".git" or relative.startswith(".git/"):
                continue
            paths.append(relative)
            if item.is_symlink():
                errors.append("snapshot_symlink_not_inspected")
            lower = name.casefold()
            if lower in _NAMES or any(fnmatch.fnmatchcase(lower, pattern) for pattern in _PATTERNS):
                hints.append(relative)
            if len(paths) > max_entries:
                errors.append("snapshot_inventory_limit_exceeded")
                break
        if len(paths) > max_entries:
            break
    inventory = {
        "schema": VERSION, "scope": SCOPE, "commit_sha": commit_sha,
        "inventory_complete": not errors,
        "inspected_path_count": len(paths),
        "inspected_paths": sorted(paths),
        "package_source_paths": sorted(set(hints)),
        "errors": sorted(set(errors)),
        "no_declared_package_sources": not errors and not hints,
    }
    inventory['inventory_sha256'] = inventory_digest(inventory)
    return inventory
