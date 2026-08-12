from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mobile_internal_engagement_probe_v1.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("mobile_internal_engagement_probe_v1", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Locator:
    def __init__(self, label: str) -> None:
        self.label = label
        self.values: list[str] = []

    def fill(self, value: str, *args, **kwargs) -> None:
        self.values.append(value)


class _UnderlyingPage:
    def __init__(self) -> None:
        self.locators: dict[str, _Locator] = {}

    def get_by_label(self, label: str, *args, **kwargs) -> _Locator:
        return self.locators.setdefault(label, _Locator(label))


class _SingleDispatchPage:
    def __init__(self) -> None:
        self._page = _UnderlyingPage()


def test_internal_production_probe_never_invents_client_or_project_identity() -> None:
    probe = _load_probe()
    dispatch = SimpleNamespace(_SingleDispatchPage=_SingleDispatchPage)
    probe.install_internal_engagement_probe(dispatch)

    page = _SingleDispatchPage()
    page.get_by_label("Client name, optional").fill("Mobile Restart Production Proof")
    page.get_by_label("Project name, optional").fill("Exact SHA placeholder")
    page.get_by_label("Repository owner/name or GitHub URL").fill("BoneManTGRM/NICO")

    assert page._page.locators["Client name, optional"].values == []
    assert page._page.locators["Project name, optional"].values == []
    assert page._page.locators["Repository owner/name or GitHub URL"].values == ["BoneManTGRM/NICO"]


def test_both_current_production_proofs_install_internal_mode() -> None:
    for relative in (
        "scripts/mobile_restart_live_acceptance_v5.py",
        "scripts/mobile_restart_live_acceptance_v6.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "install_internal_engagement_probe(single_dispatch)" in text
