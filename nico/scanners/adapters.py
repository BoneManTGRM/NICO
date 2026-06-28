from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScannerAdapter:
    name: str
    purpose: str
    enabled: bool = False
    network_required: bool = False


BUILT_IN_SAFE_ADAPTERS = (
    ScannerAdapter(name="built_in_secret_scanner", purpose="local fixture secret-pattern detection", enabled=True),
    ScannerAdapter(name="built_in_appsec_scanner", purpose="local fixture appsec marker detection", enabled=True),
    ScannerAdapter(name="built_in_dependency_scanner", purpose="local manifest fixture detection", enabled=True),
)


def adapter_status() -> list[dict]:
    return [adapter.__dict__.copy() for adapter in BUILT_IN_SAFE_ADAPTERS]
