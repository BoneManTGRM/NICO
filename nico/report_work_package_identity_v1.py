"""Distinguish retained work-package references from replaceable finding mirrors."""
from collections.abc import Mapping
from typing import Any


def is_work_package(value: Any) -> bool:
    # Presence of either supported package-identity field defines the boundary.
    # Preserve malformed/incomplete objects too; do not fabricate missing data.
    return isinstance(value, Mapping) and ("package_id" in value or "work_package_id" in value)
