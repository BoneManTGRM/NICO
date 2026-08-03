from __future__ import annotations

from pathlib import Path


def test_production_bootstrap_imports_current_scoring_provider() -> None:
    source = Path("nico/api/comprehensive_production_bootstrap.py").read_text(encoding="utf-8")
    assert "from nico.comprehensive_native_providers_v5 import install_native_comprehensive_providers" in source
    assert "from nico.comprehensive_native_providers_v4 import install_native_comprehensive_providers" not in source
    assert "from nico.comprehensive_native_providers_v3 import install_native_comprehensive_providers" not in source
