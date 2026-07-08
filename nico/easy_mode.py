from __future__ import annotations

from typing import Any


EXPRESS_STEPS = [
    "Confirm authorization.",
    "Enter repository owner/name, client name, and project name.",
    "Run Express assessment.",
    "Review section scores, evidence, unavailable notes, and human-review gate.",
    "Download or copy the report only after evidence review.",
]

MID_STEPS = [
    "Confirm authorization.",
    "Run Express first when repository evidence is available.",
    "Use Express findings to seed QA, parity, stakeholder, roadmap, and known-risk prompts.",
    "Add real screenshots, test results, interview notes, or roadmap constraints where available.",
    "Run Mid workflow and keep missing items marked unavailable instead of invented.",
]

RETAINER_STEPS = [
    "Confirm authorization.",
    "Use Express/Mid outputs as operating context.",
    "Seed commit, PR, issue, blocker, release, and roadmap prompts from available evidence.",
    "Run Retainer Ops to produce weekly status, release readiness, and approval needs.",
    "Send client-facing updates only after human review.",
]

SCANNER_STEPS = [
    "Confirm authorization and scope.",
    "Use the same repository, customer ID, project ID, and authorized-by values as Express.",
    "Run the default dependency/static/security tools.",
    "Refresh until complete.",
    "Treat unavailable tools as missing evidence, not a clean result.",
]

REPORT_STEPS = [
    "Use the latest Express, scanner, Mid, and Retainer results as evidence.",
    "Create report package.",
    "Export Markdown, HTML, or JSON.",
    "Request final review before client delivery.",
    "Request client acceptance only after final review evidence exists.",
]


WORKFLOW_CARDS = [
    {
        "workflow": "express",
        "title": "Express Technical Health Assessment",
        "target_coverage": "90-95%",
        "difficulty": "easy",
        "one_click_goal": "Repository + authorization should be enough to produce a complete draft report.",
        "steps": EXPRESS_STEPS,
        "minimum_inputs": ["repository", "authorized", "client_name", "project_name"],
    },
    {
        "workflow": "scanner_worker",
        "title": "Scanner Worker Evidence Collection",
        "target_coverage": "score-lift support",
        "difficulty": "easy_with_scope",
        "one_click_goal": "Use the same repository and authorization fields as Express, with default tools preselected.",
        "steps": SCANNER_STEPS,
        "minimum_inputs": ["repository", "authorized", "authorized_by", "authorization_scope"],
    },
    {
        "workflow": "mid",
        "title": "Mid Technical Health Assessment",
        "target_coverage": "75-85%",
        "difficulty": "guided",
        "one_click_goal": "Auto-seed required QA/parity/stakeholder/roadmap prompts from Express evidence, then let the user add real missing proof.",
        "steps": MID_STEPS,
        "minimum_inputs": ["authorized", "client_name", "project_name"],
    },
    {
        "workflow": "retainer",
        "title": "Ongoing Product Engineering Retainer Ops",
        "target_coverage": "55-70%",
        "difficulty": "guided",
        "one_click_goal": "Auto-seed weekly operating prompts from Express/Mid evidence and classify missing operating proof.",
        "steps": RETAINER_STEPS,
        "minimum_inputs": ["authorized", "client_name", "project_name"],
    },
    {
        "workflow": "reports",
        "title": "Client Report Package",
        "target_coverage": "client-ready after review",
        "difficulty": "easy_after_evidence",
        "one_click_goal": "Create a report package from latest workflow evidence and show final-review/client-acceptance gates.",
        "steps": REPORT_STEPS,
        "minimum_inputs": ["repository", "authorized", "latest_workflow_results"],
    },
]


def _lines_from_section(section: dict[str, Any]) -> list[str]:
    label = section.get("label") or section.get("id") or "Section"
    status = section.get("status") or "unknown"
    score = section.get("score") if section.get("score") is not None else "n/a"
    lines = [f"{label}: {status} {score}/100"]
    for key in ("summary",):
        value = str(section.get(key) or "").strip()
        if value:
            lines.append(value)
    for key in ("findings", "unavailable"):
        for item in section.get(key) or []:
            lines.append(str(item))
    return lines[:8]


def _section_lines(payload: dict[str, Any], *needles: str) -> list[str]:
    sections = payload.get("sections") or []
    selected: list[str] = []
    lowered = [needle.lower() for needle in needles]
    for section in sections:
        if not isinstance(section, dict):
            continue
        haystack = f"{section.get('id', '')} {section.get('label', '')}".lower()
        if any(needle in haystack for needle in lowered):
            selected.extend(_lines_from_section(section))
    return selected


def build_easy_mode_catalog() -> dict[str, Any]:
    """Describe how every NICO section becomes as easy to run as Express."""

    return {
        "status": "ok",
        "mode": "guided_easy_mode",
        "summary": "Make every section follow the Express pattern: shared authorization, shared repository/client/project fields, one main action button, evidence-bound output, and human-review gates.",
        "workflow_cards": WORKFLOW_CARDS,
        "guardrails": [
            "Do not invent QA, parity, stakeholder, roadmap, or operating evidence.",
            "Auto-seeded prompts are draft context, not proof.",
            "Unavailable evidence must stay visible.",
            "Client delivery requires final human review and acceptance evidence.",
        ],
        "next_engineering_updates": [
            "Add one-click Easy Full Run orchestration: Express -> scanner evidence -> Mid seed -> Retainer seed -> report package.",
            "Add per-section readiness meters so users see exactly what evidence is missing.",
            "Add file/evidence upload slots for QA screenshots, stakeholder notes, roadmap docs, and release evidence.",
            "Add final-review and client-acceptance buttons beside generated report packages.",
        ],
    }


def build_easy_mode_intake(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate guided intake text for Mid and Retainer from existing evidence.

    This does not fabricate proof. It converts existing Express/scanner/report data into
    structured prompts so less-technical users can run Mid and Retainer workflows with
    the same basic flow as Express while still seeing missing evidence.
    """

    express = payload.get("express") if isinstance(payload.get("express"), dict) else payload
    repository = str(payload.get("repository") or express.get("repository") or "").strip()
    project_name = str(payload.get("project_name") or express.get("project_name") or "").strip()
    findings = [str(item) for item in express.get("findings") or []][:8]
    repairs = [str(item) for item in express.get("repairs") or []][:8]
    dependency = _section_lines(express, "dependency")
    static = _section_lines(express, "static")
    ci = _section_lines(express, "ci", "cd")
    architecture = _section_lines(express, "architecture")
    velocity = _section_lines(express, "velocity")

    qa_evidence = [
        "Seeded from Express; add real functional QA proof before client delivery.",
        *findings,
        *repairs[:4],
    ]
    parity_notes = [
        "Seeded prompt: compare web/mobile or iOS/Android behavior for the same critical flows.",
        "Missing proof: screenshots, walkthrough videos, or feature-by-feature parity table.",
    ]
    stakeholder_notes = [
        f"Repository/project context: {repository or project_name or 'not specified'}.",
        "Missing proof: stakeholder goals, pain points, success metrics, constraints, and desired outcomes.",
    ]
    roadmap_notes = [
        "Seeded from Express technical findings and repair suggestions.",
        *dependency[:4],
        *static[:4],
        *architecture[:4],
    ]
    known_risks = [
        "Evidence-bound risks seeded from current report sections.",
        *dependency[:3],
        *static[:3],
        *ci[:3],
    ]

    commit_summary = [
        "Seeded prompt: summarize recent commits or attach GitHub commit evidence.",
        *velocity[:5],
    ]
    pr_summary = [
        "Seeded prompt: summarize current PRs, merged PRs, failed PRs, and open review items.",
        *ci[:5],
    ]
    issue_summary = [
        "Seeded from Express findings and repairs.",
        *findings,
        *repairs[:5],
    ]
    blockers = [
        "Human-review blockers remain until evidence is attached.",
        *dependency[:4],
        *static[:4],
    ]
    release_notes = [
        "Seeded prompt: attach release notes, smoke-test evidence, deployment state, and CI status.",
        *ci[:5],
    ]
    retainer_roadmap = [
        "Seeded prompt: weekly roadmap progress, next milestones, technical debt, and resourcing needs.",
        *roadmap_notes[:8],
    ]

    return {
        "status": "ok",
        "mode": "easy_intake_seed",
        "repository": repository,
        "client_name": payload.get("client_name") or express.get("client_name") or "",
        "project_name": project_name,
        "mid_prefill": {
            "qa_evidence": "\n".join(qa_evidence),
            "parity_notes": "\n".join(parity_notes),
            "stakeholder_notes": "\n".join(stakeholder_notes),
            "roadmap_notes": "\n".join(roadmap_notes),
            "known_risks": "\n".join(known_risks),
        },
        "retainer_prefill": {
            "commit_summary": "\n".join(commit_summary),
            "pr_summary": "\n".join(pr_summary),
            "issue_summary": "\n".join(issue_summary),
            "blockers": "\n".join(blockers),
            "release_notes": "\n".join(release_notes),
            "roadmap_notes": "\n".join(retainer_roadmap),
        },
        "missing_evidence_prompts": [
            "Add QA screenshots/videos/test results for Mid QA scoring.",
            "Add parity matrix for platform parity scoring.",
            "Add stakeholder notes for discovery/roadmap scoring.",
            "Add commit/PR/issue/release evidence for Retainer scoring.",
            "Add final review and client acceptance evidence before delivery.",
        ],
        "guardrail": "Seeded text is workflow guidance, not verified proof. NICO must keep unavailable evidence visible until real artifacts are attached.",
    }
