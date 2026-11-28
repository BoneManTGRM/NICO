"""Exact identity shape used by the Comprehensive browser intake."""
import re

_RUN_ID = re.compile(r"comprun_[0-9a-f]{32}")


def is_canonical_run_id(value: object) -> bool:
    return type(value) is str and _RUN_ID.fullmatch(value) is not None
