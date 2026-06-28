# NICO — Neural Intelligence Cyber Operations

**Tagline:** Autonomous cyber defense through Reparodynamics.

NICO is a local-first defensive cybersecurity platform. It scans authorized local repositories and safe test fixtures, detects cyber drift, ranks repairs with RYE, generates targeted TGRM repair plans, verifies outcomes, and stores repair memory.

## Safety boundary

NICO is defensive only. It does not perform unauthorized scanning, exploitation, credential theft, phishing, malware, stealth, evasion, persistence, destructive activity, authentication bypass, or offensive attack automation.

## Quick start

```bash
pip install -r requirements.txt
python -m nico scan-test-lab
python -m nico scan-drift-demo
python -m nico report latest
python -m nico verify latest
python -m nico memory
python -m nico policy show
pytest
python run_local.py
```

Open API docs at `http://localhost:8000/docs`.

Frontend:

```bash
cd apps/web
npm install
npm run lint
npm run build
npm run dev
```

Open `http://localhost:3000`.
