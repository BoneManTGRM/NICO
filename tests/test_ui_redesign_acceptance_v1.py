from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "docs" / "ui-redesign-acceptance.md"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
WORKFLOW_CALLOUT = ROOT / "apps" / "web" / "app" / "WorkflowCallout.tsx"


def test_redesign_contract_is_expert_led_and_mobile_bounded() -> None:
    source = ACCEPTANCE.read_text(encoding="utf-8")

    assert "expert-led technical advisory engagement" in source
    assert "one client-safe notice" in source
    assert "resumes that run" in source
    assert "375px and 430px" in source
    assert "collapsed by default" in source
    assert "No horizontal scrolling" in source


def test_layout_loads_geist_and_assessment_route_has_no_duplicate_banner() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")
    callout = WORKFLOW_CALLOUT.read_text(encoding="utf-8")

    assert 'import {Geist, Geist_Mono} from "next/font/google"' in layout
    assert "geistSans.variable" in layout
    assert "geistMono.variable" in layout
    assert 'pathname.startsWith("/assessment")' in callout
    assert 'pathname.startsWith("/es/assessment")' in callout
    assert "return null" in callout
