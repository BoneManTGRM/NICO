from __future__ import annotations

from pathlib import Path


PAGE = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "page.tsx"


def _source() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_public_home_is_comprehensive_only_server_redirect() -> None:
    source = _source()

    assert 'from "next/navigation"' in source or "from 'next/navigation'" in source
    assert "redirect(" in source
    assert "/assessment?tier=comprehensive#assessment" in source


def test_legacy_express_mid_selector_is_not_public_surface() -> None:
    source = _source()

    forbidden = [
        'type AssessmentType = "express" | "mid"',
        'aria-label="Assessment type"',
        '>Express</button>',
        '>Mid</button>',
        "Run fresh Express assessment",
        "Run fresh Mid assessment",
        "${API_URL}/assessment/mid-run",
        "Unified Mid run:",
        "Retainer Operations",
    ]
    for fragment in forbidden:
        assert fragment not in source


def test_public_home_has_no_client_side_redirect_fallback() -> None:
    source = _source()

    assert '"use client"' not in source
    assert "'use client'" not in source
    assert "useLayoutEffect" not in source
    assert "usePathname" not in source
    assert "window.location" not in source
