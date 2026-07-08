"""NICO package."""

from nico.hosted_metadata_auth import install_metadata_auth_for_hosted_assessment
from nico.hosted_dependency_normalization import patch_hosted_assessment_dependency_parsing

install_metadata_auth_for_hosted_assessment()
patch_hosted_assessment_dependency_parsing()

__version__ = "0.1.0"
