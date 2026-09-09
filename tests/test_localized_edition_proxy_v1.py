import subprocess


def test_localized_edition_proxy_preserves_authentication_and_scope():
    result = subprocess.run(
        ['node', '--test', 'tests/js/localized-edition-proxy.test.cjs'],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
