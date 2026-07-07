from pathlib import Path


def test_package_policy_mentions_react_major_updates():
    policy = Path('.github/dependabot.yml').read_text(encoding='utf-8')

    assert 'dependency-name: react' in policy
    assert 'dependency-name: react-dom' in policy
    assert 'version-update:semver-major' in policy


def test_audit_workflow_keeps_evidence_artifact_when_frontend_install_fails():
    workflow = Path('.github/workflows/audit-evidence.yml').read_text(encoding='utf-8')

    assert 'npm install --legacy-peer-deps' in workflow
    assert 'npm install unavailable' in workflow
    assert 'npm audit unavailable' in workflow
