"""Dependency tokenization preserves owned evidence and legacy shell quoting."""
import shlex

import pytest

from nico import assessment_cpp_project_compiler as compiler


@pytest.mark.parametrize('body', [
    ' /work/source/a.h /work/source/b.h',
    '\t/work/source/a.h\r\n /work/source/b.h ',
    ' /work/source/a.h /work/source/a.h',
    ' "/work/source/a.h" /work/source/b.h',
    " '/work/source/a.h' /work/source/b.h",
    ' /work/source/\\a.h /work/source/b.h',
])
def test_fast_and_complex_lists_match_legacy_populations(monkeypatch, body):
    targets = {path.removeprefix('/work/source/'): 'a' * 64
               for path in shlex.split(body, comments=False, posix=True)}
    request = {'targets': targets, 'generated_files': {}}
    # Independently derive the expected immutable original population.
    expected = (targets, {}, [])
    calls = []
    original = compiler.shlex.split

    def observed(value, **kwargs):
        calls.append(value)
        return original(value, **kwargs)

    monkeypatch.setattr(compiler.shlex, 'split', observed)
    result = compiler._dependency_populations(('nico_unit:' + body).encode(), request)
    assert result == expected
    complex_input = any(c in body for c in ('"', "'", '\\')) or not body.isascii()
    assert bool(calls) == complex_input


@pytest.mark.parametrize('body', ['', ' /etc/passwd', ' /work/source/../../etc/passwd',
                                  ' "/work/source/a.h',
                                  ' "/work/source/with space.h"',
                                  ' /work/source/ñ.h',
                                  ' /work/source/a.h\u00a0/work/source/b.h'])
def test_parser_keeps_empty_escape_and_malformed_rejection(body):
    request = {'targets': {'a.h': 'a' * 64}, 'generated_files': {}}
    with pytest.raises(ValueError):
        compiler._dependency_populations(('nico_unit:' + body).encode(), request)
