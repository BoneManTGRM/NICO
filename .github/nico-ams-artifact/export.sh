#!/usr/bin/env bash
# Local proposal. Run only after same-job no-network synthetic proof succeeded.
set -Eeuo pipefail
umask 077
[[ ${GITHUB_REPOSITORY:-} == BoneManTGRM/NICO &&
   ${GITHUB_REF:-} == refs/heads/atlas-synthetic-restore-20261119 &&
   ${RUNNER_ARCH:-} == X64 && ${GITHUB_SHA:-} =~ ^[0-9a-f]{40}$ ]]
# Run and prove the exact existing workflow before accepting any image.
bash .github/nico-synthetic-restore/run-ci.sh
id=$(docker inspect --type=image --format '{{.Id}}' nico-github-restore-fixture:local)
[[ $id =~ ^sha256:[0-9a-f]{64}$ ]]
out="${RUNNER_TEMP:?}/nico-fake-runtime-output"
mkdir "$out"
# The qualified image marks fixture directories 0555. Stream them directly
# from /opt so no host-side copy needs to create children in those dirs.
docker run --rm --network none --read-only --cpus 1 --memory 512m --pids-limit 32 \
    --entrypoint /bin/tar "$id" -C /opt --format=pax \
    --pax-option=delete=atime,delete=ctime --sort=name --mtime=@0 \
    --owner=0 --group=0 --numeric-owner -czf - nico-python nico-reader \
    > "$out/fake-runtime.tar.gz"
sha=$(sha256sum "$out/fake-runtime.tar.gz"); sha=${sha%% *}
python3 .github/nico-ams-artifact/verify_runtime_tar.py "$out/fake-runtime.tar.gz" "$sha"
printf 'FAKE_RUNTIME_EXPORT sha256=%s image=%s commit=%s run_id=%s\n' "$sha" "$id" "$GITHUB_SHA" "${GITHUB_RUN_ID:?}"
