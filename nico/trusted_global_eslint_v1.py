"""Image-owned ESLint parses checked-out source data without project execution.

No package installation, repository config/plugin/module resolution, NODE_OPTIONS,
or repository PATH is permitted by this separate static scanner contract.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from nico.worker_execution import WorkerLimits

VERSION = "nico.trusted-global-eslint.v1"
# These are existing Dockerfile pins, not customer-selectable runtime settings.
PINS = {"eslint": "9.39.3", "@typescript-eslint/parser": "8.65.0"}
MODULE_ROOTS = (Path("/usr/local/lib/node_modules"), Path("/usr/lib/node_modules"))
NODE_BINARIES = (Path("/usr/local/bin/node"), Path("/usr/bin/node"))
EXCLUDED = frozenset({".git", ".venv", "venv", "node_modules", ".next", "dist",
                      "build", "coverage", "coverage_html", "__pycache__"})
SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"})
PROJECT_DENIAL = "Project-aware ESLint remains disabled without NICO_ALLOW_PROJECT_COMMANDS=true."


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular(path: Path, root: Path) -> Path:
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("trusted_eslint_regular_file_required")
    resolved = path.resolve(strict=True)
    resolved.relative_to(root.resolve(strict=True))
    return resolved


def _trusted_tools() -> dict:
    """Only fixed image directories; never inspect customer package entry points."""
    node = next((p for p in NODE_BINARIES
                 if p.exists() and not p.is_symlink() and p.is_file()
                 and os.access(p, os.X_OK)), None)
    if node is None:
        raise ValueError("trusted_global_node_unavailable")
    for root in MODULE_ROOTS:
        try:
            if not root.is_dir() or root.is_symlink():
                continue
            files = {
                "eslint_package": root / "eslint/package.json",
                "parser_package": root / "@typescript-eslint/parser/package.json",
                "eslint_binary": root / "eslint/bin/eslint.js",
                "eslint_api": root / "eslint/lib/api.js",
                "parser_entry": root / "@typescript-eslint/parser/dist/index.js",
            }
            resolved = {name: _regular(path, root) for name, path in files.items()}
            for package, key in (("eslint", "eslint_package"),
                                 ("@typescript-eslint/parser", "parser_package")):
                metadata = json.loads(resolved[key].read_text(encoding="utf-8"))
                if metadata.get("name") != package or metadata.get("version") != PINS[package]:
                    raise ValueError("trusted_global_eslint_package_identity_mismatch")
            return {"node": node.resolve(strict=True), **resolved,
                    "file_sha256": {name: _hash_file(path) for name, path in resolved.items()}}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    raise ValueError("trusted_global_eslint_image_prerequisites_unverified")


def _population(repo: Path) -> dict[str, str]:
    from nico.node_scanner_applicability_v1 import _qt_translation

    if repo.is_symlink() or not repo.is_dir():
        raise ValueError("trusted_eslint_source_root_invalid")
    population = {}
    entries = 0
    for parent, directories, filenames in os.walk(repo, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in EXCLUDED)
        for name in directories:
            if (Path(parent) / name).is_symlink():
                raise ValueError("trusted_eslint_source_directory_symlink")
        for name in sorted(filenames):
            entries += 1
            if entries > 100_000:  # Existing node input inventory bound.
                raise ValueError("trusted_eslint_source_inventory_incomplete")
            path = Path(parent) / name
            if path.suffix.lower() not in SUFFIXES:
                continue
            path = _regular(path, repo)
            relative = path.relative_to(repo.resolve(strict=True)).as_posix()
            if path.suffix.lower() == ".ts" and _qt_translation(path, relative) is not None:
                continue
            population[relative] = _hash_file(path)
    return dict(sorted(population.items()))


def _config(parser_entry: Path) -> str:
    return (
        "const tsParser = require(" + json.dumps(str(parser_entry)) + ");\n"
        "module.exports = [\n"
        " { files: ['**/*.{[jJ][sS],[jJ][sS][xX],[mM][jJ][sS],[cC][jJ][sS]}'], languageOptions: { ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } }, rules: { 'no-constant-condition': 'error', 'no-dupe-keys': 'error', 'no-func-assign': 'error', 'no-import-assign': 'error', 'no-unreachable': 'error', 'valid-typeof': 'error' } },\n"
        " { files: ['**/*.{[tT][sS],[tT][sS][xX]}'], languageOptions: { parser: tsParser, parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true }, project: false, projectService: false } }, rules: { 'no-constant-condition': 'error', 'no-dupe-class-members': 'error', 'no-fallthrough': 'error', 'no-self-assign': 'error', 'no-unreachable': 'error', 'no-undef': 'off', 'no-unused-vars': 'off' } }\n"
        "];\n"
    )


def _program(eslint_api: Path) -> str:
    # Customer paths are JSON data. No shell or project-controlled JavaScript runs.
    return (
        "'use strict';\nconst fs = require('node:fs');\n"
        "const { ESLint } = require(" + json.dumps(str(eslint_api)) + ");\n"
        "async function main() {\n"
        " const a = process.argv.slice(2);\n"
        " if (a.length !== 4 || a[0] !== '--config' || a[2] !== '--inputs') throw new Error('invalid trusted ESLint invocation');\n"
        " const inputs = JSON.parse(fs.readFileSync(a[3], 'utf8'));\n"
        " if (!Array.isArray(inputs) || inputs.some(p => typeof p !== 'string')) throw new Error('invalid source input list');\n"
        " const scanner = new ESLint({ overrideConfigFile: a[1], ignore: false, cache: false, allowInlineConfig: false });\n"
        " const results = await scanner.lintFiles(inputs);\n"
        " process.stdout.write(JSON.stringify(results));\n"
        " process.exitCode = results.some(r => r.errorCount > 0 || r.fatalErrorCount > 0) ? 1 : 0;\n"
        "}\nmain().catch(() => { process.stderr.write('Trusted global ESLint execution failed.\\n'); process.exitCode = 2; });\n"
    )


def run_global_static_eslint(spec, workspace, runner):
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.scanner_execution_receipt_v1 import write_generated_config

    def unavailable(reason):
        return pipeline._unavailable(spec, reason + " " + PROJECT_DENIAL, source=VERSION)

    try:
        tools = _trusted_tools()
        population = _population(workspace.repo_dir)
        if not population:
            return unavailable("No applicable JavaScript or TypeScript source inputs were found.")
        # Generated executable/config/input data cannot live in the assessed tree.
        root = workspace.root.resolve(strict=True)
        repo = workspace.repo_dir.resolve(strict=True)
        output = root / "trusted-global-eslint"
        if output.is_symlink():
            return unavailable("Trusted scanner output directory is a symlink.")
        output.mkdir(exist_ok=True)
        output.resolve(strict=True).relative_to(root)
        if output.resolve(strict=True) == repo or repo in output.resolve(strict=True).parents:
            return unavailable("Trusted scanner output directory overlaps assessed source.")
        for name in ("config.cjs", "runner.cjs", "inputs.json", "version.txt"):
            if (output / name).is_symlink():
                return unavailable("Trusted scanner generated input is a symlink.")
        config, program, inputs = (output / name for name in ("config.cjs", "runner.cjs", "inputs.json"))
        write_generated_config(config, _config(tools["parser_entry"]))
        write_generated_config(program, _program(tools["eslint_api"]))
        source_paths = [str(repo / name) for name in population]
        write_generated_config(inputs, json.dumps(source_paths, separators=(",", ":")) + "\n")
        home = output / "home"
        if home.is_symlink():
            return unavailable("Trusted scanner home directory is a symlink.")
        home.mkdir(exist_ok=True)
        env = {"HOME": str(home), "PATH": "/usr/local/bin:/usr/bin:/bin",
               "NODE_PATH": "", "NODE_OPTIONS": "", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        version_file = output / "version.txt"
        version_result = pipeline._run(
            runner, (str(tools["node"]), str(tools["eslint_binary"]), "--version"),
            cwd=output, limits=WorkerLimits(5, 1024), stdout_path=version_file, extra_env=env)
        version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else ""
        if (version_result.returncode != 0 or version_result.timed_out
                or version_result.output_truncated or version != "v" + PINS["eslint"]):
            return unavailable("Trusted image ESLint native version could not be verified.")
        raw = root / "scanner-raw" / "eslint.json"
        command = (str(tools["node"]), str(program), "--config", str(config), "--inputs", str(inputs))
        result = pipeline._run(
            runner, command, cwd=repo,
            limits=WorkerLimits(spec.timeout_seconds, max(spec.max_output_chars, 16_000_000)),
            stdout_path=raw, extra_env=env)
        payload, reason = pipeline._read_json(raw)
        complete = isinstance(payload, list)
        findings = []
        observed = []
        native_error_count = 0
        expected_paths = {str(repo / name): name for name in population}
        if complete:
            for row in payload:
                if not isinstance(row, dict) or not isinstance(row.get("filePath"), str):
                    complete = False
                    break
                # Native path strings must match the requested frozen population;
                # do not resolve an untrusted output path against unrelated files.
                relative = expected_paths.get(row["filePath"])
                if relative is None or not isinstance(row.get("messages"), list):
                    complete = False
                    break
                messages = row["messages"]
                if (any(not isinstance(message, dict) or type(message.get("severity")) is not int
                        or message["severity"] not in {1, 2} for message in messages)
                        or any(type(row.get(key)) is not int or row[key] < 0
                               for key in ("errorCount", "warningCount", "fatalErrorCount"))):
                    complete = False
                    break
                # ESLint emits rule-less warnings for ignored/unconfigured files.
                # These rows acknowledge a path but do not prove it was parsed.
                if any(message["severity"] == 1 and message.get("ruleId") is None
                       for message in messages):
                    complete = False
                    reason = "Native ESLint acknowledged an input without verified parsing."
                    break
                errors = sum(message["severity"] == 2 for message in messages)
                warnings = sum(message["severity"] == 1 for message in messages)
                fatal = sum(message.get("fatal") is True for message in messages)
                if (row["errorCount"] != errors or row["warningCount"] != warnings
                        or row["fatalErrorCount"] != fatal or fatal > errors):
                    complete = False
                    break
                native_error_count += errors
                observed.append(relative)
                findings.extend({**message, "filePath": row["filePath"]} for message in messages)
            complete = (complete and len(observed) == len(set(observed))
                        and set(observed) == set(population)
                        and result.returncode == int(native_error_count > 0))
        try:
            unchanged = _population(repo) == population
        except (OSError, ValueError):
            unchanged = False
        if not unchanged:
            complete = False
            reason = "Source inputs changed during trusted static analysis."
        if not complete:
            reason = reason or "Native ESLint result population does not match frozen source inputs."
        blob = pipeline._raw_blob(spec.name, raw, "json")
        return pipeline._tool_payload(
            spec, result, findings=findings, capture_complete=complete, reason=reason,
            raw_blob=blob, execution_source=VERSION, workspace=workspace,
            valid_returncodes={0, 1},
            extra={"scanner_tool_version": PINS["eslint"], "project_commands_executed": False,
                   "repository_configuration_loaded": False, "trusted_tool_files_sha256": tools["file_sha256"],
                   "generated_config_sha256": _hash_file(config), "trusted_runner_sha256": _hash_file(program),
                   "input_list_sha256": _hash_file(inputs), "required_input_count": len(population),
                   "observed_input_count": len(observed), "source_input_hashes": population,
                   "scanner_invocation_receipts": [version_result.scanner_execution_receipt, result.scanner_execution_receipt]})
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return unavailable("Trusted global ESLint identity, source boundary or complete output could not be verified.")
