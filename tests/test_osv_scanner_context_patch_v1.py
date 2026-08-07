from __future__ import annotations

from pathlib import Path

from nico.osv_scanner_context_patch_v1 import (
    VERSION,
    _enrich_fallback_result,
    install_osv_scanner_context_patch,
    parse_osv_findings_with_context,
)


def _modern_osv_payload() -> dict:
    return {
        "results": [
            {
                "source": {
                    "path": "/tmp/nico/source/requirements.txt",
                    "type": "lockfile",
                },
                "packages": [
                    {
                        "package": {
                            "name": "pillow",
                            "version": "9.5.0",
                            "ecosystem": "PyPI",
                        },
                        "groups": [{"ids": ["GHSA-example"]}],
                        "vulnerabilities": [
                            {
                                "id": "GHSA-example",
                                "summary": "example advisory",
                                "affected": [
                                    {
                                        "package": {
                                            "name": "libwebp-sys2",
                                            "ecosystem": "crates.io",
                                        }
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_osv_parser_preserves_scanned_package_version_and_manifest() -> None:
    findings = parse_osv_findings_with_context(_modern_osv_payload())

    assert len(findings) == 1
    finding = findings[0]
    assert finding["id"] == "GHSA-example"
    assert finding["package"] == "pillow"
    assert finding["installed_version"] == "9.5.0"
    assert finding["ecosystem"] == "PyPI"
    assert finding["dependency_path"] == "/tmp/nico/source/requirements.txt"
    assert finding["osv_scanned_package"] == "pillow"
    assert finding["osv_scanned_version"] == "9.5.0"
    assert finding["scanner_context_schema"] == VERSION

    # Nested affected-package metadata must remain advisory evidence only. It
    # must not replace the package identity OSV actually scanned.
    assert finding["affected"][0]["package"]["name"] == "libwebp-sys2"
    assert finding["package"] != "libwebp-sys2"


def test_osv_parser_supports_legacy_package_shape() -> None:
    findings = parse_osv_findings_with_context(
        {
            "packages": [
                {
                    "package": {
                        "name": "idna",
                        "version": "3.9.0",
                        "ecosystem": "PyPI",
                    },
                    "source": {"path": "requirements.txt"},
                    "vulns": [{"id": "GHSA-idna"}],
                }
            ]
        }
    )

    assert findings == [
        {
            "id": "GHSA-idna",
            "package": "idna",
            "osv_scanned_package": "idna",
            "installed_version": "3.9.0",
            "osv_scanned_version": "3.9.0",
            "ecosystem": "PyPI",
            "osv_scanned_ecosystem": "PyPI",
            "dependency_path": "requirements.txt",
            "dependency_manifest_source": {"path": "requirements.txt"},
            "scanner_context_schema": VERSION,
        }
    ]


def test_osv_api_fallback_context_preserves_dependency_source() -> None:
    class FakeRunners:
        @staticmethod
        def _osv_query_dependencies(repo_dir: Path) -> list[dict[str, str]]:
            return [
                {
                    "name": "idna",
                    "version": "3.18",
                    "ecosystem": "PyPI",
                    "source": "requirements.txt",
                }
            ]

        @staticmethod
        def redact_payload(value):
            return value

    result = _enrich_fallback_result(
        {
            "status": "completed",
            "findings": [
                {
                    "id": "GHSA-example",
                    "package": "idna",
                    "installed_version": "3.18",
                }
            ],
        },
        Path("."),
        FakeRunners,
    )
    finding = result["findings"][0]

    assert finding["package"] == "idna"
    assert finding["installed_version"] == "3.18"
    assert finding["ecosystem"] == "PyPI"
    assert finding["dependency_path"] == "requirements.txt"
    assert finding["scanner_context_schema"] == VERSION


def test_runtime_installer_binds_context_aware_osv_adapters() -> None:
    from nico import scanner_tool_runners as runners

    status = install_osv_scanner_context_patch()
    findings = runners._osv_findings(_modern_osv_payload())

    assert status["parser_bound"] is True
    assert status["fallback_bound"] is True
    assert findings[0]["package"] == "pillow"
    assert findings[0]["installed_version"] == "9.5.0"


def test_requirements_pin_resolved_pillow_and_idna_versions() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "pillow==12.3.0" in requirements
    assert "idna==3.18" in requirements
