from __future__ import annotations

from .agents import DEFENSIVE_AGENTS
from .memory_firewall import memory_access_allowed
from .permissions import agent_can


def plan_agent_task(agent_key: str, action: str, memory_zone: str | None = None, approved: bool = False) -> dict:
    agent = DEFENSIVE_AGENTS[agent_key]
    action_allowed = agent_can(agent_key, action, approved=approved)
    memory_decision = {"allowed": True, "reason": "not_requested"}
    if memory_zone:
        memory_decision = memory_access_allowed(agent.memory_zones, memory_zone, approved=approved)
    return {
        "agent": agent.name,
        "action": action,
        "allowed": bool(action_allowed and memory_decision["allowed"]),
        "memory": memory_decision,
        "approval_required": action in {"mutate", "export"} and not approved,
    }


def swarm_policy() -> dict:
    return {"agents": sorted(agent.name for agent in DEFENSIVE_AGENTS.values()), "mode": "local_defensive_foundation"}
