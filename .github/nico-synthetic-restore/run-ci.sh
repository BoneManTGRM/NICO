#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ ${GITHUB_REPOSITORY:-} = BoneManTGRM/NICO ]]
[[ ${GITHUB_REF:-} = refs/heads/atlas-synthetic-restore-20261119 ]]
[[ ${RUNNER_ARCH:-} = X64 ]]
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
src=.github/nico-synthetic-restore
python3 - "$src" "$root" <<'PY'
import hashlib, json, shutil, sys
from pathlib import Path
source, build = map(Path, sys.argv[1:])
for name in ("Dockerfile", "qualify.py", "runner.sh", "requirements.lock",
             "native_import_probe.py", "native_reader.py",
             "native_pg18_driver.py", "synthetic_fixture.py"):
    shutil.copyfile(source / name, build / name)
manifest = json.loads((source / "native-source-manifest.json").read_text())
if manifest["revision"] != "5eb768b5776f88bae86e972c76267915cc874c85" or len(manifest["files"]) != 39:
    raise SystemExit("unexpected source manifest")
sha256 = {}
for name, digest in manifest["files"].items():
    p = Path(name)
    if p.is_absolute() or ".." in p.parts or p.parts[0] != "nico" or p.suffix != ".py":
        raise SystemExit("source path")
    data = p.read_bytes()
    git_blob = b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data
    if p.is_symlink() or hashlib.sha1(git_blob).hexdigest() != digest:
        raise SystemExit("source hash")
    dest = build / "native-source" / p
    dest.parent.mkdir(exist_ok=True, parents=True)
    dest.write_bytes(data)
    sha256[name] = hashlib.sha256(data).hexdigest()
(build / "native-source-manifest.json").write_text(json.dumps({"revision":manifest["revision"],"files":sha256}))
PY
# Build-only, official hash-pinned wheels; never in the running rehearsal.
python3 -m pip --isolated download --index-url https://pypi.org/simple \
    --no-deps --no-cache-dir --require-hashes --only-binary=:all: \
    --platform manylinux2014_x86_64 --implementation cp --python-version 3.13 \
    --abi cp313 -r "$root/requirements.lock" -d "$root/wheels"

pin() {
  [[ $1 = docker.io/library/python:3.13.18-slim-bookworm || $1 = docker.io/library/postgres:18.6-bookworm ]]
  docker buildx imagetools inspect --raw "$1" |
   python3 -c 'import json,re,sys; d=json.load(sys.stdin); a=[m["digest"] for m in d["manifests"] if m.get("platform",{}).get("os")=="linux" and m.get("platform",{}).get("architecture")=="amd64"]; assert len(a)==1 and re.fullmatch(r"sha256:[a-f0-9]{64}",a[0]); print(sys.argv[1]+"@"+a[0])' "$1"
}
py=$(pin docker.io/library/python:3.13.18-slim-bookworm)
pg=$(pin docker.io/library/postgres:18.6-bookworm)
printf 'SYNTHETIC_BASE_IMAGES %s %s\n' "$py" "$pg"
docker build --platform linux/amd64 --network none --build-arg PYTHON_IMAGE="$py" \
  --build-arg POSTGRES_IMAGE="$pg" --tag nico-github-restore-fixture:local "$root"
docker run --rm --network none --cpus 1 --memory 1g --pids-limit 128 \
  -e NICO_CI_FIXTURE_MODE=github-synthetic-no-network nico-github-restore-fixture:local
