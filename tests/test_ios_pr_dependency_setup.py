"""Keep PR native-browser installation on the established production setup."""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/ios-webkit-paint-proof.yml'


def step(text, name):
    return text.split('      - name: ' + name + '\n', 1)[1].split('\n      - name:', 1)[0]


def test_pr_webkit_uses_same_bounded_official_apt_setup_as_live_proof():
    text = WORKFLOW.read_text()
    pr = step(text, 'Install and prepare pinned WebKit lifecycle dependency for PR proof')
    live = step(text, 'Install pinned WebKit proof dependency')
    start = '          if [ -f /etc/apt/apt-mirrors.txt ]; then'
    end = '          timeout --signal=TERM --kill-after=30s 12m python -m playwright install --with-deps webkit'
    assert start in pr
    assert pr[pr.index(start):pr.index(end)] == live[live.index(start):live.index(end)]
    assert 'https://archive.ubuntu.com/ubuntu/' in pr
    for option in ('Acquire::Retries "3";', 'Acquire::http::Timeout "20";', 'Acquire::https::Timeout "20";'):
        assert option in pr
    assert 'timeout-minutes: 15' in pr and end in pr
    assert '"playwright==1.61.0"' in pr and '"pytest==9.1.1"' in pr
    assert 'python scripts/prepare_playwright_webkit_native_visibility_v1.py' in pr
    for bypass in ('--allow-unauthenticated', 'trusted=yes', 'Verify-Peer', '--no-sandbox', 'continue-on-error', '|| true'):
        assert bypass not in pr
    proof = step(text, 'Prove installed WebKit observes native tab lifecycle')
    assert "if: github.event_name == 'pull_request'" in proof
    assert 'NICO_PROOF_WEBKIT_NATIVE_VISIBILITY: "1"' in proof
    assert '-k installed_webkit_observes_real_browser_visibility' in proof
