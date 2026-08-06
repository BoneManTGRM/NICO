# NICO Comprehensive Candidate-Triage Report

**AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED**

- Repository: `BoneManTGRM/NICO`
- Exact assessed commit: `9c876ba4e3e9bb152de52567232038e52a6bbb3e`
- Evidence basis: two deterministic scanner passes over the exact assessed commit
- Canonical candidate population: **662**
- Confirmed material findings: **0 before authorized human review**
- Human approval: **not granted**

## Reconciliation

| Category | Canonical candidates |
|---|---:|
| Static | 586 |
| Dependency | 59 |
| Secret | 17 |
| **Total** | **662** |

The two scanner passes produced 667 raw nonzero observations. The canonical register contains 662 candidates after retaining one record for each of four exact duplicate TruffleHog observations and recording one unverified `.env.example` template observation in the exclusion ledger. Nothing is silently deleted.

## Proposed dispositions

| Proposed disposition | Count |
|---|---:|
| `dependency_reachability_and_upgrade_review` | 59 |
| `source_review_required` | 586 |
| `test_fixture_confirmation_required` | 17 |

All dispositions are proposals. None constitutes human approval, risk acceptance, or confirmation that a candidate is exploitable or harmless.

## Excluded-observation ledger

| Reason | Count |
|---|---:|
| `exact_duplicate_scanner_observation` | 4 |
| `unverified_example_template_observation` | 1 |

## Integrity controls

- Stable unique candidate identities: **True**
- Stable cluster identities: **20 clusters**
- Two-run candidate parity: **verified**
- Raw secret material in register and report: **omitted**
- Client delivery: **blocked pending authorized human review**

The complete candidate records are retained in `candidate-register.json` and `candidate-register.csv`; cluster mappings are in `candidate-clusters.json`.
