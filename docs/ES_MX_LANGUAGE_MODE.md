# NICO Español (México)

NICO supports a Mexican Spanish report mode through the `express_es_mx` assessment mode and the `/es-mx` frontend route.

## Frontend

- English command center: `/`
- Spanish command center: `/es-mx`

The Spanish page sends:

```json
{
  "assessment_mode": "express_es_mx"
}
```

## Backend behavior

When `assessment_mode`, `language`, or `report_language` indicates `es-MX`, NICO localizes the final scored result after evidence scoring is complete.

This means:

- Scoring stays unchanged.
- Evidence rules stay unchanged.
- Missing evidence stays visible.
- Spanish output does not inflate scores.

## Output

Spanish mode returns:

- `report_language: "es-MX"`
- `language_label: "Español (México)"`
- Spanish section labels
- Spanish status labels
- Spanish Markdown report
- Spanish HTML report with `lang="es-MX"`

## Safety rule

Translation is presentation-only. NICO must not change evidence, findings, unavailable-data notes, or scores just because Spanish mode is selected.
