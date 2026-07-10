from __future__ import annotations

from pathlib import Path


def test_no_server_tls_context_sets_modern_minimum() -> None:
    source = Path('nico/no_server_assessment.py').read_text(encoding='utf-8')
    assert 'context.minimum_version = ssl.TLSVersion.TLSv1_2' in source


def test_cli_scan_repo_uses_resolved_safe_paths() -> None:
    source = Path('nico/cli.py').read_text(encoding='utf-8')
    assert 'safe_scan_files' in source
    assert 'relative_to(root)' in source
    assert 'path.is_symlink()' in source


def test_api_blocked_responses_do_not_return_raw_payloads() -> None:
    source = Path('nico/api/main.py').read_text(encoding='utf-8')
    assert 'safe_blocked_exception' in source
    assert "HTTPException(400, result)" not in source
