#!/usr/bin/env bash
# Local CI images only. No service credentials or assessment execution.
set -euo pipefail
containers=()
cleanup() {
  local container
  for container in "${containers[@]}"; do
    timeout 1s docker logs "$container" || true
    timeout 2s docker rm -f "$container" || true
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for image in nico-ci:ci nico-web-ci:ci; do
  docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}} user={{.Config.User}}' "$image"
  container=$(docker create --network=none --entrypoint sh "$image" -c 'sleep 85')
  containers+=("$container")
  docker start "$container" >/dev/null
  expected_user=nico
  if [[ "$image" == nico-web-ci:ci ]]; then expected_user=node; fi
  docker exec -i "$container" sh -s -- "$expected_user" <<'SH'
set -eu
id
test "$(id -un)" = "$1"
node -p 'JSON.stringify({node:process.version,arch:process.arch,platform:process.platform})'
node -e 'if (process.versions.node.split(".")[0] !== "24") process.exit(1)'
npm --version
npx --version
test "$(npm --version)" = 10.8.2
test "$(npx --version)" = 10.8.2
ldd "$(command -v node)" > /tmp/node-ldd.txt 2>&1
cat /tmp/node-ldd.txt
if grep -E 'not found|Error loading|Error relocating' /tmp/node-ldd.txt; then exit 1; fi
SH
  if [[ "$image" == nico-ci:ci ]]; then
    docker exec -i "$container" sh -s <<'SH'
set -eu
test -w /data
command -v nico
command -v nico-api
python -c 'from nico.api.production import app; assert app'
eslint --version
tsc --version
cd /tmp
printf 'const value = 1;\n' > /tmp/nico-node-smoke.js
eslint --no-config-lookup --rule 'no-undef:error' /tmp/nico-node-smoke.js
printf 'const value: number = 1;\n' > /tmp/nico-node-smoke.ts
tsc --noEmit --strict --skipLibCheck /tmp/nico-node-smoke.ts
SH
  fi
done

# No published ports or external network: request deployment metadata over
# loopback inside the container. This route never launches work.
web=$(docker create --network=none \
  -e NICO_FRONTEND_RELEASE_SHA="$(git rev-parse HEAD)" nico-web-ci:ci)
containers+=("$web")
docker start "$web" >/dev/null
docker exec -i "$web" node <<'JS'
const deadline = Date.now() + 30000;
(async () => {
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch('http://127.0.0.1:3000/api/deployment', {signal: AbortSignal.timeout(2000)});
      const body = await response.json();
      if (response.status !== 200 || body.frontend_commit !== process.env.NICO_FRONTEND_RELEASE_SHA
          || body.human_review_required !== true || body.client_delivery_allowed !== false) {
        throw new Error(`Invalid local deployment response: ${JSON.stringify(body)}`);
      }
      console.log(JSON.stringify({route:'/api/deployment', status:response.status, body}));
      return;
    } catch (error) { lastError = error; }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw lastError || new Error('Local web startup deadline exceeded');
})().catch(error => { console.error(error); process.exitCode = 1; });
JS
