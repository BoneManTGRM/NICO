import json

import pytest

from nico.assessment_cpp_production_selection import configure_first_readiness, select_configure_first_contract
from tests.test_cpp_production_selection import env, repo_step, RELEASE


def test_readiness_matches_selector_without_exposing_values_or_claiming_execution():
    values = {**env(), 'DATABASE_URL': 'secret-database-credential'}
    result = configure_first_readiness(environ=values, release_revision=RELEASE)
    assert result['selection_settings_valid'] is True
    assert select_configure_first_contract(repo_step(), environ=values, release_revision=RELEASE) is not None
    assert result['evidence_scope'] == 'configuration_only'
    assert result['native_run_success_inferred'] is False
    assert all(value not in json.dumps(result) for value in (values['DATABASE_URL'], values['NICO_CPP_CONFIGURE_FIRST_IMAGE_CONFIG_ID'], RELEASE))


@pytest.mark.parametrize('key,value,reason', [
    ('NICO_CPP_CONFIGURE_FIRST_ENABLED', '0', 'enabled'),
    ('NICO_ASSESSMENT_WORKER_DISPATCH_ENABLED', '0', 'dispatch_enabled'),
    ('NICO_CPP_CONFIGURE_FIRST_IMAGE_CONFIG_ID', 'invalid', 'image_configured'),
    ('NICO_CPP_CONFIGURE_FIRST_QUALIFIED_RELEASE', 'f' * 40, 'release_bound'),
    ('NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_RUN_ID', '0', 'qualification_receipt_configured'),
    ('NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_ARTIFACT_SHA256', 'invalid', 'qualification_receipt_configured'),
])
def test_readiness_identifies_the_same_fail_closed_selector_condition(key, value, reason):
    values = {**env(), key: value}
    result = configure_first_readiness(environ=values, release_revision=RELEASE)
    assert result['selection_settings_valid'] is False
    assert result['reason'] == reason + '_not_satisfied'
    assert select_configure_first_contract(repo_step(), environ=values, release_revision=RELEASE) is None
