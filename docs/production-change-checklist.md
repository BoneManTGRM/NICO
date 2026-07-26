# Production change checklist

- [ ] Contract, unit, integration, and build checks are green on the pull request.
- [ ] Review the client-safe unavailable state at 375px, 430px, 768px, and desktop widths.
- [ ] Confirm Strategic human-evidence modules remain optional and fail closed.
- [ ] Confirm repository authorization is still required.
- [ ] Confirm no intake request is emitted when readiness is blocked.
- [ ] Confirm a retry with an existing run ID performs a status recovery, not a second intake.
- [ ] Configure production Postgres or a verified persistent volume.
- [ ] Verify the runtime diagnostic reports container-replacement-safe persistence.
- [ ] Deploy the exact merge SHA to frontend and backend.
- [ ] Run two consecutive live Strategic assessments against the exact deployed SHA.
- [ ] Confirm both runs have distinct IDs and preserve identity through reconnect.
- [ ] Confirm client delivery remains blocked until human approval.
