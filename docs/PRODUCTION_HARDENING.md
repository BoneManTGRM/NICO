# Production Hardening Roadmap

Before hosted SaaS deployment, harden NICO itself:

- auth
- RBAC
- organization isolation
- encrypted secrets
- scanner sandboxing
- worker isolation
- rate limits
- safe CORS
- CSRF where relevant
- audit logs
- signed webhooks
- backup/restore
- kill switch
- approval workflows
- admin action logging
- no raw secret storage
- secure report permissions

The current pass keeps local-first mode as the priority and does not force production SaaS assumptions into the MVP.
