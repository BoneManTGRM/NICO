from copy import deepcopy
import pytest


def test_profile_is_disabled_and_no_launch_occurs():
    from nico.typescript_isolation_profile_v1 import disabled_profile, validate_profile, planned_container_arguments
    profile=disabled_profile()
    assert validate_profile(profile)['enabled'] is False
    assert profile['os_isolation_verified'] is False
    args=planned_container_arguments(profile, 'ghcr.io/bonemantgrm/nico/assessment-typescript@sha256:'+'a'*64)
    assert '--network=none' in args and '--read-only' in args
    assert '--cap-drop=ALL' in args and '--user=10001:10001' in args
    assert '--cpus=0.5' in args and '--memory=512m' in args and '--pids-limit=32' in args
    assert not any('socket' in x or x.startswith('--volume') for x in args)


@pytest.mark.parametrize('field,value',[('enabled',True),('os_isolation_verified',True),('network','bridge'),('user','root'),('cpus','4'),('memory_bytes',2**30),('host_mounts',['/workspace']),('capabilities',['SYS_ADMIN'])])
def test_relaxed_or_activated_profile_rejected(field,value):
    from nico.typescript_isolation_profile_v1 import disabled_profile, validate_profile
    profile=disabled_profile(); profile[field]=value
    with pytest.raises(ValueError): validate_profile(profile)


def test_mutable_tag_or_wrong_image_rejected():
    from nico.typescript_isolation_profile_v1 import disabled_profile, planned_container_arguments
    for image in ['node:latest','ghcr.io/bonemantgrm/nico/assessment-typescript:latest','other@sha256:'+'a'*64]:
        with pytest.raises(ValueError): planned_container_arguments(disabled_profile(),image)
