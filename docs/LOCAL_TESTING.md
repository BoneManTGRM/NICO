# Local Testing

Backend smoke checks:

```bash
python -m nico scan-test-lab
python -m nico scan-drift-demo
python -m nico scan ./nico/test_lab/sample_repo
python -m nico report latest
python -m nico verify latest
python -m nico memory
python -m nico policy show
pytest
```

Frontend checks:

```bash
cd apps/web
npm install
npm run lint
npm run build
npm run dev
```

`npm run dev` is long-running and should start a local server at `http://localhost:3000`.
