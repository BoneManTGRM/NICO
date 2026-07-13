# Security Policy

## Defensive-use boundary

NICO is defensive-only. It must not be used for unauthorized scanning, exploitation, credential theft, phishing, malware, stealth, evasion, persistence, destructive activity, authentication bypass, or offensive attack automation.

Only assess repositories, systems, archives, or staging targets you own or are explicitly authorized to review.

## Reporting a vulnerability

Do not open a public issue when a report could expose:

- credentials, tokens, private keys, or personal data;
- a bypass of authorization, review, tenancy, or delivery controls;
- a vulnerability in a live NICO deployment;
- private repository or client evidence;
- a practical exploitation path; or
- an integrity weakness that could create false green, approved, or client-ready states.

Report the issue privately to the repository owner through a private GitHub or established direct contact channel. Include only the minimum information necessary to reproduce the problem safely.

A useful report contains:

1. affected commit or release;
2. affected route, module, or workflow;
3. prerequisites and authorization scope;
4. safe reproduction steps using synthetic data;
5. expected and observed behavior;
6. security, privacy, or evidence-integrity impact;
7. suggested mitigation when known; and
8. whether credentials or private data may have been exposed.

Do not send live credentials. Revoke and rotate any credential that may have been exposed before sharing diagnostic evidence.

## High-priority report categories

- authorization or tenancy bypass
- admin-token or delivery-token exposure
- secret-redaction failure
- report, approval, receipt, or artifact hash mismatch
- false passing evidence or score inflation
- unsafe subprocess execution
- path traversal or archive extraction weakness
- persistent cross-customer data exposure
- destructive action without explicit approval
- deployment-identity or release-gate bypass

## Response expectations

The maintainer will attempt to acknowledge a complete private report promptly, assess severity, preserve evidence, and prepare a narrowly scoped repair. Timing depends on reproducibility, impact, and maintainer availability; no fixed service-level agreement is promised.

A fix is not considered complete until regression coverage and relevant CI checks pass. Production-impacting fixes should also verify the deployed frontend/backend commit and rollback path.

## Supported versions

The actively maintained version is the current `main` branch and its verified deployments. Historical commits, previews, forks, and unverified deployments may not receive fixes.

## Disclosure

Coordinate public disclosure with the maintainer. Allow reasonable time for repair and deployment. Never publish secrets, private client data, raw delivery tokens, or unnecessary exploitation detail.

## Safe research

Use synthetic fixtures and isolated environments. Stop testing when you encounter private data, credentials, cross-tenant access, destructive behavior, or a target outside the authorized scope.
