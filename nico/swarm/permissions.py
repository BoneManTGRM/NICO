from __future__ import annotations

from .agents import DEFENSIVE_AGENTS


def agent_can(agent_key: str, action: str, approved: bool = False) -> bool:
    agent = DEFENSIVE_AGENTS[agent_key]
    if action == "mutate":
        return agent.can_mutate and approved
    if action == "export":
        return agent.can_export and approved
    return action in agent.allowed_tools


def permission_matrix() -> dict:
    return {
        key: {
            "tools": agent.allowed_tools,
            "memory_zones": agent.memory_zones,
            "can_mutate": agent.can_mutate,
            "can_export": agent.can_export,
        }
        for key, agent in DEFENSIVE_AGENTS.items()
    }
