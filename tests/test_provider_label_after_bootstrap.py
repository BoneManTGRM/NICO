def test_final_bootstrap_localizes_provider_label_but_preserves_machine_evidence():
    from nico.api.specialist_ship_ready_bootstrap import app
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree

    for provider in ('GitHub', 'GitLab', 'Bitbucket Cloud', 'Azure DevOps'):
        value = f'Provider: {provider}.'
        assert _localize_tree({'evidence': [value]})['evidence'] == [f'Proveedor: {provider}.']

    value = 'snapshot.provider: GitLab'
    assert _localize_tree({'evidence': [value]})['evidence'] == [value]
