# Post-638 production verification

Verification baseline: immutable main commit `dbbca3671e8620d115ac25cbbbf2c74f25f28a90`.

This branch is verification-only and must not be merged. It exists to exercise terminal completion, durable-record blocking, truth/review gate ordering, and Express release metadata before production evidence is accepted.

Release evidence still required outside CI:

- Vercel and Railway must report the exact merged SHA.
- A fresh Express run must complete at 100 with all required gates terminal.
- The exact run must remain retrievable after a backend restart from Postgres or a verified persistent volume.
- The final PDF must be 15–20 substantive pages and must be inspected page by page.
- Two consecutive production runs on the same immutable commit must pass.
