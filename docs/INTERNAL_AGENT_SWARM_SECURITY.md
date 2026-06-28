# NICO Internal Agent Swarm Security

This document describes the planned local-only foundation for controlled internal defensive agent swarms in NICO.

NICO's swarm model is not unrestricted agent automation. It is a controlled defensive workflow where specialized agents have least-privilege tools, scoped memory zones, audit records, and approval gates.

## Defensive roles

- Scan Agent
- Drift Agent
- RYE Scoring Agent
- TGRM Repair Agent
- Verification Agent
- Memory Agent
- Compliance Agent
- Report Agent
- Connector Guard Agent
- Swarm Supervisor Agent

## Safety boundaries

- Report Agent cannot mutate files.
- Repair Agent cannot apply production changes without approval.
- Connector Guard Agent cannot access raw secrets.
- Secret memory is blocked from raw access.
- External connector access is disabled by default.

This is a local-only foundation. It is not hosted SaaS behavior and does not perform live external scanning.
