"""Local proxy control; no external network, credentials, or scanner execution."""
import http.server
import threading

from nico import scanner_worker, snapshot_scanner_worker


def test_network_environment_keeps_only_explicit_proxy_configuration(monkeypatch, tmp_path):
    values = {
        'HTTP_PROXY': 'http://127.0.0.1:10001',
        'HTTPS_PROXY': 'http://127.0.0.1:10002',
        'NO_PROXY': 'localhost,127.0.0.1',
        'http_proxy': 'http://127.0.0.1:10003',
        'https_proxy': 'http://127.0.0.1:10004',
        'no_proxy': 'localhost',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    for key in ('GITHUB_TOKEN', 'DATABASE_URL', 'GIT_CONFIG_COUNT', 'GIT_ASKPASS',
                'GIT_SSL_NO_VERIFY', 'SSL_CERT_FILE', 'LD_PRELOAD', 'PYTHONPATH'):
        monkeypatch.setenv(key, 'must-not-inherit')
    environment = scanner_worker.clean_env(tmp_path)
    assert environment == {
        'PATH': scanner_worker.os.getenv('PATH', ''), 'HOME': str(tmp_path),
        'TMPDIR': str(tmp_path), 'PYTHONUNBUFFERED': '1', **values,
    }


def test_empty_proxy_values_are_not_added(monkeypatch, tmp_path):
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy'):
        monkeypatch.setenv(key, '')
    assert set(scanner_worker.clean_env(tmp_path)) == {'PATH', 'HOME', 'TMPDIR', 'PYTHONUNBUFFERED'}


def test_snapshot_git_reaches_configured_local_proxy(monkeypatch, tmp_path):
    observed = []

    class Proxy(http.server.BaseHTTPRequestHandler):
        def do_CONNECT(self):
            observed.append(self.path)
            self.send_error(502, 'Synthetic proxy refuses upstream')

        def log_message(self, *args):
            pass

    with http.server.HTTPServer(('127.0.0.1', 0), Proxy) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy'):
                monkeypatch.delenv(key, raising=False)
            monkeypatch.setenv('https_proxy', f'http://127.0.0.1:{server.server_port}')
            result = snapshot_scanner_worker._git(
                ['git', 'ls-remote', 'https://scanner-network.invalid/repo.git'],
                cwd=tmp_path, env=scanner_worker.clean_env(tmp_path), timeout=5,
            )
            assert result.returncode != 0  # A proxy connection is not source verification.
            assert observed == ['scanner-network.invalid:443']
            assert '502' in result.stderr
        finally:
            server.shutdown()
            thread.join(timeout=2)
            assert not thread.is_alive()
