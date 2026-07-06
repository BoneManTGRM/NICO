# Client Job Mode v7

Client Job Mode turns NICO assessment output into a paid-audit delivery workflow.

## Purpose

The mode maps a commercial scope or quote to the evidence NICO must collect before a client-facing report can be delivered.

## Express audit package

For Express Technical Health Assessment work, NICO tracks these deliverables:

- Code audit and recent development activity
- Library and dependency ecosystem health
- CI/CD reliability and release process
- Architecture and technical debt
- Maturity semaphore by audit area
- Velocity and complexity signal
- Strategic quick wins and medium-term action plan
- Resourcing recommendation

## Product artifact review

Client Job Mode can also inspect product evidence text from screenshots, PDFs, or report samples and turn it into findings. For ABA-style report artifacts, it detects evidence such as:

- No verified picks
- Current provider gate
- Provider not matched
- Data unavailable
- Research-only recommendation
- Missing live team snapshot
- Missing lineup or injury verification

These findings are not treated as final proof by themselves. They become evidence prompts for the repository assessment and human review.

## Provider-gate root-cause prompts

When provider-gate evidence is detected, NICO prompts review of:

- API key loading and provider health checks
- Buyer-pick gate rejection rules
- Stale or duplicated saved rows
- Odds, market, lineup, injury, and team snapshot enrichment
- Report export fallback logic
- Evidence IDs for provider, timestamp, market, and rejection reason

## Delivery rule

Client Job Mode never marks a client-ready package final automatically. It can produce a draft-ready package, but human review is required before client delivery.
