#!/bin/sh
set -eu

candidate=$1
tool=$2
source_dir=$3
out=$4
producer=$5

case "$producer" in
    "" ) mkdir -m 0755 "$out"; printf '%s\n' 'Owned TypeScript inputs not packaged: no Railway build SHA.'; exit 0 ;;
    *[!0-9a-f]* ) printf '%s\n' 'Invalid Railway build SHA.' >&2; exit 1 ;;
esac
[ "${#producer}" -eq 40 ] && [ "$producer" != 0000000000000000000000000000000000000000 ]
[ "$(node --version)" = v24.22.3 ]
[ "$(npm --version)" = 11.19.1 ]
echo "a7ec1b37e6ff9d187e4198c5b6df9a4eb1c74dd31804fb3bac55cc4ceca1ac01  /usr/local/bin/node" | sha256sum --check --status

reference=/owned-reference
baseline="$tool/historical_typescript_inputs.json.gz"
python3 "$tool/stage_typecheck_reference.py" "$candidate" "$tool/historical-overlay" "$baseline" "$reference"
(
    cd "$reference/apps/web"
    npm ci --ignore-scripts --no-audit --no-fund
    # Existing protected-build proof uses this fixed framework entry, not npm scripts.
    # Build-only owned and verified public historical source, not an assessment checkout.
    node -e 'if (require("next/package.json").version !== "16.4.5" || require("typescript/package.json").version !== "6.0.3") process.exit(1)'
    CI=true NEXT_TELEMETRY_DISABLED=1 timeout --kill-after=10s 360s node ./node_modules/next/dist/bin/next build
)
PYTHONPATH="$source_dir/py" python3 "$tool/package_owned_typecheck.py" --reference "$reference" --baseline "$baseline" \
    --scripts "$source_dir/scripts" --node /usr/local/bin/node --producer "$producer" --out "$out"
