from __future__ import annotations

import json
import sys

from nico.cli import Store, main as cli_main
from nico.foundations import (
    agent_security_scan_demo,
    approvals_pending_demo,
    audit_latest_demo,
    bench_demo,
    connector_policy_demo,
    cyber_twin_demo,
    sandbox_scanner_demo,
    swarm_policy_demo,
    tenant_demo,
    vault_demo,
)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> None:
    args = sys.argv[1:]
    command = tuple(args[:2])

    if command == ("swarm", "policy"):
        _emit(swarm_policy_demo())
        return
    if command == ("agent-security", "scan-demo"):
        _emit(agent_security_scan_demo())
        return
    if command == ("vault", "demo"):
        _emit(vault_demo())
        return
    if command == ("connector", "policy"):
        _emit(connector_policy_demo())
        return
    if command == ("sandbox", "scanner-demo"):
        _emit(sandbox_scanner_demo())
        return
    if command == ("audit", "latest"):
        _emit(audit_latest_demo(Store().rows("audit_log")[:25]))
        return
    if command == ("approvals", "pending"):
        _emit(approvals_pending_demo())
        return
    if command == ("tenant", "demo"):
        _emit(tenant_demo())
        return
    if command == ("cyber-twin", "demo"):
        _emit(cyber_twin_demo())
        return
    if command == ("bench", "demo"):
        _emit(bench_demo())
        return

    cli_main(args)


if __name__ == "__main__":
    main()
