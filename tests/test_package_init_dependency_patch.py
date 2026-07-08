from nico import hosted_assessment


def test_package_init_installs_hosted_dependency_patch():
    deps = hosted_assessment.parse_requirements("PyJWT[crypto]==2.13.0\n")
    assert deps == [
        {
            "name": "PyJWT",
            "operator": "==",
            "version": "2.13.0",
            "ecosystem": "PyPI",
            "source": "requirements.txt",
        }
    ]
