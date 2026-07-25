# Decision-Grade Cost of Inaction

Version: `nico.decision_grade_cost_engine.v1`

## Purpose

NICO may describe the consequence of leaving a finding unresolved, but it must not fabricate financial precision. The cost engine therefore supports three explicit modes and preserves the distinction between technical evidence and business inference.

## Modes

### Qualitative

Used when no defensible operating or financial inputs exist.

The finding retains one of the bounded exposure levels:

- Minimal
- Limited
- Material
- Severe
- Critical

No monetary amount is emitted.

### Scenario

Uses disclosed low, base, and high planning ranges. The default scenario contains engineering-hour ranges by priority and bounded category multipliers. These are planning assumptions, not observed client labor, market benchmarks, or quoted implementation prices.

Dollar conversion occurs only when both a currency and a defensible conversion input are supplied. Without those inputs, the report shows engineering-hour exposure only.

### Client input

Uses client-supplied finding, category, or default exposure ranges. Client-input mode requires:

- a source reference;
- disclosed assumptions;
- at least one quantitative estimate;
- a currency whenever any monetary conversion input is present.

Findings without an applicable client estimate remain qualitative. NICO does not extrapolate one finding's estimate across unrelated findings unless the client explicitly supplies a category or default range.

## Deterministic formula

For each low, base, and high case:

```text
exposure = direct cost
         + engineering hours × blended engineering cost per hour
         + release-delay days × release-delay cost per day
```

The report records:

- input ranges;
- rates used or marked not supplied;
- formula;
- timeframe;
- low, base, and high result;
- currency when applicable;
- confidence;
- source;
- assumptions.

## Input contract

The report builder reads `cost_of_inaction_inputs` from the structured assessment payload or report identity.

Example client-input payload:

```json
{
  "mode": "client_input",
  "source": "Client financial intake 2026-07-25",
  "currency": "USD",
  "timeframe_days": 90,
  "blended_engineering_cost_per_hour": 125,
  "release_delay_cost_per_day": 2500,
  "assumptions": [
    "The supplied blended engineering rate is valid for the 90-day planning period."
  ],
  "finding_estimates": {
    "RISK-P1-EXAMPLE": {
      "engineering_hours_low": 40,
      "engineering_hours_base": 80,
      "engineering_hours_high": 120,
      "release_delay_days_low": 0,
      "release_delay_days_base": 2,
      "release_delay_days_high": 5,
      "confidence": "moderate"
    }
  }
}
```

Example scenario payload:

```json
{
  "mode": "scenario",
  "scenario_profile": "balanced",
  "source": "NICO planning scenario",
  "assumptions": [
    "Scenario values are planning ranges and are not client actuals."
  ]
}
```

Supported scenario profiles are `conservative`, `balanced`, and `stress`.

## Validation and failure behavior

Invalid client inputs are not partially used. NICO:

1. retains qualitative exposure;
2. records `cost_of_inaction_inputs_invalid`;
3. marks delivery readiness `Delivery Blocked`;
4. emits no unsupported monetary amount.

The engine does not modify technical scores, evidence confidence, finding priority, or residual risk.

## Report integration

The cost result is stored in each canonical finding and therefore appears in:

- structured decision-grade JSON;
- Executive Risk Register;
- detailed finding sections;
- Markdown and HTML reports;
- PDF report;
- backlog exports.

The Assumption Register records whether inputs were client supplied or scenario based and identifies findings that remain unquantified.
