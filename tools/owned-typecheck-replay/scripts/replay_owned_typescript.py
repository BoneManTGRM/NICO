"""CI-only comparison of the read-only compiler to a pinned, public owned build."""
from __future__ import annotations

import argparse
from hashlib import sha256
import gzip
import json
import os
from pathlib import Path
import shutil
import sys

from nico import nico_ci_typescript_typegen_inputs_v1 as sealer
from nico import nico_typescript_confined_bridge_v1 as bridge

BASELINE_SHA = "aec46d5ca31e19f6d7e62b65d98f8e116396782f0e164a1a7d289e5f484878f4"
REFERENCE_ARTIFACT = "4f51458ba63b7f37f85f58f0361ef62a5d6c62cd40571e3db662ae539ece9e6e"
OUTER_TOOL_READS = frozenset((
    "@compiler/package.json", "@compiler/lib/typescript.js", "apps/web/package-lock.json",
))


def bytes_exact(path: Path, expected: str, limit: int = 8 * 1024 * 1024) -> bytes:
    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_file():
        raise ValueError("reference input is not a regular canonical file")
    with path.open("rb") as f:
        raw = f.read(limit + 1)
    if len(raw) > limit or sha256(raw).hexdigest() != expected:
        raise ValueError("reference input digest mismatch")
    return raw


def canonical(trace_path: str) -> str:
    if trace_path.startswith("/project/apps/web/"):
        return trace_path.removeprefix("/project/")
    if trace_path.startswith("/compiler/lib/"):
        return "@compiler/lib/" + trace_path.removeprefix("/compiler/lib/")
    raise ValueError("unexpected compiler trace namespace")


def replay(target: Path, proof_ref: str) -> int:
    scripts = Path(__file__).resolve().parent
    with gzip.open(scripts / "historical_typescript_inputs.json.gz", "rb") as f:
        material = f.read(256 * 1024 + 1)
    if len(material) > 256 * 1024 or sha256(material).hexdigest() != BASELINE_SHA:
        raise ValueError("baseline digest mismatch")
    known = json.loads(material)
    reads = known["read_inputs"]
    inventory = known["source_inventory"]
    compiler = known["compiler"]
    if (known["source_sha"], compiler["version"], len(reads)) != (
        sealer.HISTORICAL_COMMIT, bridge.COMPILER_VERSION, 785
    ):
        raise ValueError("baseline identity mismatch")

    # Build inputs have been produced by the exact checkout and never published.
    compiler_base = target / "apps/web/node_modules/typescript"
    source = {}
    for name, digest in inventory.items():
        if name.startswith("apps/web/"):
            source[name.removeprefix("apps/web/")] = bytes_exact(target / name, digest)
    dependency, compiler_lib = {}, {}
    for name, digest in reads.items():
        if name.startswith("apps/web/node_modules/"):
            dependency[name.removeprefix("apps/web/node_modules/")] = bytes_exact(target / name, digest)
        elif name.startswith("@compiler/lib/") and name.endswith(".d.ts"):
            leaf = name.removeprefix("@compiler/lib/")
            compiler_lib[leaf] = bytes_exact(compiler_base / "lib" / leaf, digest)
    bytes_exact(compiler_base / "lib/typescript.js", reads["@compiler/lib/typescript.js"], 32 * 1024 * 1024)
    bytes_exact(compiler_base / "package.json", reads["@compiler/package.json"])
    bytes_exact(target / "apps/web/package-lock.json", reads["apps/web/package-lock.json"])

    assessed = bridge.AssessedIdentity(sealer.REPO, sealer.HISTORICAL_COMMIT, sealer.HISTORICAL_TREE)
    pin = sealer.TrustedTypegenPin(
        proof_ref, assessed.commit, assessed.tree, sealer.inventory_digest(inventory), REFERENCE_ARTIFACT,
        tuple(sorted((Path(name).name, digest) for name, digest in known["generated_inputs"].items())),
    )
    fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        sealed = sealer.seal_private_build_inputs(fd, pin)
    finally:
        os.close(fd)
    generated = sealer.admit_private_build_inputs(
        sealed, pin, assessed_commit=assessed.commit, assessed_tree=assessed.tree,
        verified_source_inventory=inventory,
    )
    mounts = dict(source=source, generated=generated, dependencies=dependency, compilerLibs=compiler_lib)
    if not bridge._source_mount_matches_inventory(source, inventory):
        raise ValueError("source mount mismatch")
    policy = bridge.OwnedTypeScriptPolicy(
        proof_ref, pin, tuple(sorted((name, bridge._mount_digest(files)) for name, files in mounts.items())),
    )
    node = Path(shutil.which("node") or "").resolve(strict=True)
    driver, host = (scripts / "nico_typecheck_confined_driver_v1.cjs",
                    scripts / "nico_typecheck_virtual_host_v1.cjs")
    tool = bridge.TrustedCompiler(
        node, compiler["node_sha256"], compiler["node_version"],
        driver, sha256(driver.read_bytes()).hexdigest(), host, sha256(host.read_bytes()).hexdigest(),
        compiler_base / "lib/typescript.js", compiler["entry_sha256"], compiler["package_sha256"],
        compiler["version"],
    )
    # The hosted job owns this short-lived workspace, not a root-installed
    # production tree. The process/file permissions and exact hashes still apply.
    bridge._verify_runtime(tool, immutable=False)
    wire, nonce = bridge._prepare_wire(policy, assessed, tool.node_version, tool.compiler_version, mounts)
    observed = bridge._validated_response(bridge._capture(tool, wire, timeout=120), nonce, assessed, tool)
    roots = [canonical(x) for x in observed["roots"]]
    program = [canonical(x) for x in observed["program_inputs"]]
    trace = {canonical(k): v for k, v in observed["read_inputs"].items()}
    expected_trace = {path: digest for path, digest in reads.items() if path not in OUTER_TOOL_READS}
    omissions = expected_trace.keys() - trace.keys()
    unexpected = trace.keys() - expected_trace.keys()
    mismatches = sum(trace[k] != expected_trace[k] for k in trace.keys() & expected_trace.keys())
    result = {
        "compiler_version": observed["compiler_version"], "roots": len(roots), "program_files": len(program),
        "compiler_read_files": len(trace), "separately_verified_toolchain_and_lock_inputs": len(OUTER_TOOL_READS),
        "omissions": len(omissions), "unexpected_reads": len(unexpected), "changed_reads": mismatches,
        "diagnostics": len(observed["diagnostics"]),
        "same_roots": sorted(roots) == sorted(known["root_inputs"]),
        "same_program": sorted(program) == known["program_inputs"],
        "genuine_assessment": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["same_roots"] and result["same_program"] and not any((
        omissions, unexpected, mismatches, result["diagnostics"]
    )) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--proof-ref", required=True)
    args = parser.parse_args()
    try:
        raise SystemExit(replay(args.target.resolve(strict=True), args.proof_ref))
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print(f"Owned compiler proof stopped: {type(exc).__name__}. No report was produced.", file=sys.stderr)
        raise SystemExit(1)
