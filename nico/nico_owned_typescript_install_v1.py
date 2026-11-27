"""Read the sealed image inputs for the exact ordinary owned TypeScript profile."""
from __future__ import annotations

import gzip
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat

from nico import nico_ci_typescript_typegen_inputs_v1 as sealer
from nico import nico_typescript_confined_bridge_v1 as bridge

ROOT = Path("/opt/nico-owned-typecheck")
BASELINE_SHA = "aec46d5ca31e19f6d7e62b65d98f8e116396782f0e164a1a7d289e5f484878f4"
INVENTORY_SHA = "f436fa16f743cecf57e349f73361f2bbee307404e8eaac669fb22d7c8c4c7e8c"
REFERENCE_ARTIFACT = "4f51458ba63b7f37f85f58f0361ef62a5d6c62cd40571e3db662ae539ece9e6e"
SCHEMA = "nico.owned-typescript-install.v1"
_SHA = re.compile(r"[a-f0-9]{40}\Z")
_TOOLCHAIN_READS = frozenset((
    "@compiler/package.json", "@compiler/lib/typescript.js", "apps/web/package-lock.json",
))


def _provider_producer() -> str:
    owner = os.environ.get("RAILWAY_GIT_REPO_OWNER", "")
    repo = os.environ.get("RAILWAY_GIT_REPO_NAME", "")
    producer = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
    if (owner.casefold(), repo.casefold(), os.environ.get("RAILWAY_GIT_BRANCH")) != ("bonemantgrm", "nico", "main") or not _SHA.fullmatch(producer):
        raise ValueError("producer_identity_unavailable")
    return producer


def _immutable_reader(path: Path, maximum: int) -> bytes:
    # Do not follow links or accept a root-owned file in a replaceable directory.
    if path.resolve(strict=True) != path:
        raise ValueError("installed_input_path_not_canonical")
    for parent in path.parents:
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022 or os.access(parent, os.W_OK):
            raise ValueError("installed_input_directory_not_immutable")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as file:
        before = os.fstat(file.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                or before.st_mode & 0o022 or os.access(path, os.W_OK) or before.st_size > maximum):
            raise ValueError("installed_input_not_immutable")
        raw = file.read(maximum + 1)
        after = os.fstat(file.fileno())
    if len(raw) != before.st_size or len(raw) > maximum or (
        before.st_size, before.st_mtime_ns, before.st_ctime_ns
    ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("installed_input_changed")
    return raw


def _source_blob(repo_dir: Path, relative: str, expected: str) -> bytes:
    path = repo_dir / relative
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError("assessed_source_path_not_regular")
    with path.open("rb") as file:
        data = file.read(bridge.MAX_INPUT_MEMBER_BYTES + 1)
    if len(data) > bridge.MAX_INPUT_MEMBER_BYTES or sha256(data).hexdigest() != expected:
        raise ValueError("assessed_source_bytes_mismatch")
    return data


def _trace_path(name: str) -> str:
    if name.startswith("/project/apps/web/"):
        return name.removeprefix("/project/")
    if name.startswith("/compiler/lib/"):
        return "@compiler/lib/" + name.removeprefix("/compiler/lib/")
    raise ValueError("native_path_namespace_mismatch")


def _check_native_parity(known: dict, native: dict) -> None:
    roots = sorted(_trace_path(x) for x in native["roots"])
    program = sorted(_trace_path(x) for x in native["program_inputs"])
    observed = {_trace_path(k): v for k, v in native["read_inputs"].items()}
    expected = {k: v for k, v in known["read_inputs"].items() if k not in _TOOLCHAIN_READS}
    if (native["compiler_version"] != bridge.COMPILER_VERSION or native["diagnostics"]
            or roots != sorted(known["root_inputs"]) or program != known["program_inputs"]
            or observed != expected):
        raise ValueError("native_reference_parity_mismatch")


def observe(repo_dir: Path, *, target_repo: str, target_commit: str, target_tree: str) -> dict | None:
    """Return None only for out-of-scope targets or an intentionally absent install."""
    if target_repo != sealer.REPO or target_commit != sealer.HISTORICAL_COMMIT:
        return None
    if not ROOT.exists() and not ROOT.is_symlink():
        return None
    try:
        if ROOT.is_dir() and not ROOT.is_symlink() and not any(ROOT.iterdir()):
            return None  # Local or non-Git builds explicitly ship no install.
        if target_tree != sealer.HISTORICAL_TREE or os.geteuid() == 0:
            raise ValueError("assessed_identity_or_service_user_invalid")
        producer = _provider_producer()
        manifest = json.loads(_immutable_reader(ROOT / "manifest.json", 64 * 1024))
        if (manifest["schema"], manifest["producer_commit"], manifest["target_commit"], manifest["target_tree"],
                manifest["baseline_sha256"], manifest["source_inventory_sha256"]) != (
                SCHEMA, producer, target_commit, target_tree, BASELINE_SHA, INVENTORY_SHA):
            raise ValueError("installed_identity_mismatch")
        zipped = _immutable_reader(ROOT / "historical_typescript_inputs.json.gz", 128 * 1024)
        with gzip.GzipFile(fileobj=BytesIO(zipped)) as handle:
            raw = handle.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024 or sha256(raw).hexdigest() != BASELINE_SHA:
            raise ValueError("installed_baseline_digest_mismatch")
        known = json.loads(raw)
        inventory = known["source_inventory"]
        if (known["source_sha"] != target_commit or sealer.inventory_digest(inventory) != INVENTORY_SHA
                or len(known["read_inputs"]) != 785):
            raise ValueError("installed_baseline_identity_mismatch")
        compiler = known["compiler"]
        if (manifest["node_version"], manifest["node_sha256"], manifest["compiler_version"],
                manifest["compiler_entry_sha256"], manifest["compiler_package_sha256"]) != (
                compiler["node_version"], compiler["node_sha256"], compiler["version"],
                compiler["entry_sha256"], compiler["package_sha256"]):
            raise ValueError("installed_toolchain_pin_mismatch")
        sealed = _immutable_reader(ROOT / "generated.zip", sealer.MAX_ARCHIVE)
        if sha256(sealed).hexdigest() != manifest["generated_bundle_sha256"]:
            raise ValueError("installed_bundle_digest_mismatch")

        pin = sealer.TrustedTypegenPin(
            producer, target_commit, target_tree, INVENTORY_SHA, REFERENCE_ARTIFACT,
            tuple(sorted((Path(name).name, digest) for name, digest in known["generated_inputs"].items())),
        )
        source = {}
        repo_dir = repo_dir.resolve(strict=True)
        for name, digest in inventory.items():
            if name.startswith("apps/web/"):
                source[name.removeprefix("apps/web/")] = _source_blob(repo_dir, name, digest)
        deps, libs = {}, {}
        for name, digest in known["read_inputs"].items():
            if name.startswith("apps/web/node_modules/"):
                destination, prefix, root = deps, "apps/web/node_modules/", ROOT / "dependencies"
            elif name.startswith("@compiler/lib/") and name.endswith(".d.ts"):
                destination, prefix, root = libs, "@compiler/lib/", ROOT / "typescript/lib"
            else:
                continue
            relative = name.removeprefix(prefix)
            content = _immutable_reader(root / relative, bridge.MAX_INPUT_MEMBER_BYTES)
            if sha256(content).hexdigest() != digest:
                raise ValueError("installed_dependency_digest_mismatch")
            destination[relative] = content

        assessed = bridge.AssessedIdentity(target_repo, target_commit, target_tree)
        runtime = bridge.TrustedCompiler(
            ROOT / "node", compiler["node_sha256"], compiler["node_version"],
            ROOT / "scripts/nico_typecheck_confined_driver_v1.cjs", manifest["driver_sha256"],
            ROOT / "scripts/nico_typecheck_virtual_host_v1.cjs", manifest["host_sha256"],
            ROOT / "typescript/lib/typescript.js", compiler["entry_sha256"], compiler["package_sha256"], compiler["version"],
        )
        policy = bridge.OwnedTypeScriptPolicy(producer, pin, tuple(sorted(manifest["mount_digests"].items())))
        result = bridge.run_owned_native_bridge(
            policy=policy, verified_producer_commit=producer, assessed=assessed, verified_source_inventory=inventory,
            source_mount=source, private_generated_bundle=sealed, dependency_mount=deps, compiler_lib_mount=libs,
            runtime=runtime,
        )
        if result.get("outcome") == "compiler_observed":
            _check_native_parity(known, result["native"])
            result["producer_commit"] = producer
            result["target_commit"] = target_commit
            result["target_tree"] = target_tree
        return result
    except (KeyError, ValueError, TypeError, OSError, EOFError):
        return {"outcome": "unavailable", "reason": "owned_typescript_install_or_parity_unverified"}
