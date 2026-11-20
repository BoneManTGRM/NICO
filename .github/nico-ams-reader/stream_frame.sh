#!/bin/bash
# FAKE DATA ONLY. Never point this lab script at a source server.
set -euo pipefail
umask 077
test "${NICO_FRAME_TEST_ONLY:-}" = 'fixed-local-synthetic'
test -z "${RAILWAY_SERVICE_ID:-}${RAILWAY_ENVIRONMENT_ID:-}"
test "$#" = 4
cert=$1
key=$2
out=$3
run=$4
[[ "$run" =~ ^[0-9a-f]{32}$ ]]
[[ -f "$cert" && -f "$key" && "$out" = /* && ! -e "$out" && ! -L "$out" ]]
mkdir -m700 -- "$out"
export LC_ALL=C PATH=/usr/bin:/bin
export NICO_CERT="$cert" NICO_RUN="$run"
test -r "$NICO_CERT"
# This process reads fake fixture bytes only. Each child receives bounded input
# via stdin; no plaintext chunk file is created. The signed ordered manifest
# binds run ID, recipient digest and exact frame bytes.
(
  cd "$out"
  timeout -s TERM -k 3s 30s split -b 1048576 -d -a 4 --filter='
    case "$FILE" in (part-000[0-7]) ;; (*) exit 91 ;; esac
    timeout -s TERM -k 1s 8s openssl cms -encrypt -binary -aes-256-gcm -outform DER "$NICO_CERT" >"$FILE.cms"
  ' - part-
  shopt -s nullglob
  parts=(part-*.cms)
  test "${#parts[@]}" -ge 1
  test "${#parts[@]}" -le 8
  {
    printf 'NICO-SYNTHETIC-FRAME-V1 %s\n' "$NICO_RUN"
    openssl x509 -in "$NICO_CERT" -outform DER | sha256sum | cut -d ' ' -f 1
    printf '%s\n' "${#parts[@]}"
    i=0
    for name in "${parts[@]}"; do
      printf -v expected 'part-%04d.cms' "$i"
      [[ "$name" = "$expected" && ! -L "$name" ]]
      size=$(wc -c <"$name")
      ((size>0 && size<=1052672))
      digest=$(sha256sum -- "$name" | cut -d ' ' -f 1)
      printf '%s %s %s\n' "$name" "$size" "$digest"
      i=$((i+1))
    done
  } >manifest.incomplete
  timeout -s TERM -k 1s 8s openssl pkeyutl -sign -rawin -inkey "$key" -in manifest.incomplete -out manifest.sig.incomplete
  mv manifest.sig.incomplete manifest.sig
  mv manifest.incomplete manifest.complete
)
