# Railway build

Railway was failing during the optional web dependency install because the Dockerfile used npm ci in apps/web.

The Dockerfile now uses npm install with legacy peer deps and ignored scripts for that install step.
