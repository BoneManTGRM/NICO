"""Bounded, conservative evidence for a native OSV no-package result.

This inventory is only used after OSV reports exit 128. It cannot turn a tool
failure, ignored manifest, unsupported dependency file, or unreadable tree clean.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
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


def inspect_package_sources(repo: Path, *, max_entries: int = 100_000) -> dict[str, Any]:
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
    manifest = {"paths": sorted(paths), "package_source_paths": sorted(set(hints))}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": "nico.osv-package-inventory.v1",
        "inventory_complete": not errors,
        "inspected_path_count": len(paths),
        "inventory_sha256": digest,
        "package_source_paths": sorted(set(hints)),
        "errors": sorted(set(errors)),
        "no_declared_package_sources": not errors and not hints,
    }
