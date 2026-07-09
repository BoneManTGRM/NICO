# Railway deploy notes

Railway builds the production Docker image for the NICO backend service.

The previous Dockerfile used `npm ci` inside `apps/web`. That command fails when `apps/web/package-lock.json` is not exactly synced with `apps/web/package.json`.

The Dockerfile now uses `npm install --legacy-peer-deps --ignore-scripts` for the optional `apps/web` dependency install during the image build.

This keeps the backend deployment from failing on a stale frontend lockfile while keeping package scripts disabled during install.
