#!/usr/bin/env bash
# Local proposal. Run only after same-job no-network synthetic proof succeeded.
set -Eeuo pipefail
umask 077
[[ ${GITHUB_REPOSITORY:-} == BoneManTGRM/NICO &&
   ${GITHUB_REF:-} == refs/heads/atlas-synthetic-restore-20261119 &&
   ${RUNNER_ARCH:-} == X64 && ${GITHUB_SHA:-} =~ ^[0-9a-f]{40}$ ]]
scratch=$(mktemp -d)
cid=
cleanup() {
  [[ -z $cid ]] || docker rm "$cid" >/dev/null
  rm -rf -- "$scratch"
}
trap cleanup EXIT
# Run and prove the exact existing workflow before accepting any image.
bash .github/nico-synthetic-restore/run-ci.sh
id=$(docker inspect --type=image --format '{{.Id}}' nico-github-restore-fixture:local)
[[ $id =~ ^sha256:[0-9a-f]{64}$ ]]
cid=$(docker create --network none --entrypoint /bin/false "$id")
[[ $cid =~ ^[0-9a-f]{64}$ ]]
docker cp "$cid:/opt/nico-python" "$scratch/nico-python"
docker cp "$cid:/opt/nico-reader" "$scratch/nico-reader"
out="${RUNNER_TEMP:?}/nico-fake-runtime-output"
mkdir "$out"
tar -C "$scratch" --format=pax --pax-option=delete=atime,delete=ctime --sort=name \
    --mtime=@0 --owner=0 --group=0 --numeric-owner -czf "$out/fake-runtime.tar.gz" nico-python nico-reader
sha=$(sha256sum "$out/fake-runtime.tar.gz"); sha=${sha%% *}
python3 .github/nico-ams-artifact/verify_runtime_tar.py "$out/fake-runtime.tar.gz" "$sha"
printf 'FAKE_RUNTIME_EXPORT sha256=%s image=%s commit=%s run_id=%s\n' "$sha" "$id" "$GITHUB_SHA" "${GITHUB_RUN_ID:?}"
