"""Build-time checks only: no network, SQL, process daemon or credentials."""
import ctypes
import hashlib
import importlib.metadata
import json
from pathlib import Path
import ssl
import subprocess
import sys
import zlib

root = Path("/opt/nico-reader")
runtime = Path("/opt/nico-python")
manifest = json.loads((root / "native-source-manifest.json").read_text())
tree = root / "native-source"
entries = list(tree.rglob("*"))
if (manifest["revision"] != "5eb768b5776f88bae86e972c76267915cc874c85"
    or len(manifest["files"]) != 39 or any(p.is_symlink() for p in entries)
    or set(manifest["files"]) != {str(p.relative_to(tree)) for p in entries if p.is_file()}):
    raise SystemExit("fixture source set")
for relative, expected in manifest["files"].items():
    if hashlib.sha256((tree / relative).read_bytes()).hexdigest() != expected:
        raise SystemExit("fixture source digest")
if sys.version_info[:2] != (3, 13) or sys.prefix != str(runtime):
    raise SystemExit("relocated CPython")
# Check the executable and native extensions loaded by the exact rehearsal,
# not optional stdlib modules the probe never imports (e.g. Tk/readline).
import psycopg
import native_import_probe
resolved = {Path(sys.executable).resolve()}
for mod in tuple(sys.modules.values()):
    spec = getattr(mod, "__spec__", None)
    origin = getattr(spec, "origin", None)
    if not isinstance(origin, str):
        continue
    path = Path(origin)
    if path.suffix == ".so" and path.is_relative_to(runtime):
        resolved.add(path)
for path in sorted(resolved):
    link = subprocess.run(["/usr/bin/ldd", str(path)], check=True, capture_output=True,
                          timeout=8)
    missing = [line.strip() for line in link.stdout.splitlines() if b"=> not found" in line]
    if missing:
        raise SystemExit(f"missing shared library for {path.name}: {missing!r}")
if (psycopg.pq.__impl__ != "binary"
    or importlib.metadata.version("psycopg") != "3.3.4"
    or importlib.metadata.version("psycopg-binary") != "3.3.4"):
    raise SystemExit("psycopg provenance")
pg = subprocess.run(["/usr/lib/postgresql/18/bin/postgres", "--version"],
                    check=True, capture_output=True, timeout=8).stdout.split()
if len(pg) < 3 or pg[2] != b"18.6":
    raise SystemExit("expected PostgreSQL 18.6")
print("SYNTHETIC_BUILD_IMPORT_CHECK_PASSED gate_eligible=false")
