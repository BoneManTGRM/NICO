from __future__ import annotations

import base64
from copy import deepcopy

import pytest

from nico import comprehensive_exact_artifact_hash_binding_v1 as binding
from nico.comprehensive_artifact_manifest_approval_v1 import attach_artifact_manifest
from tests.test_comprehensive_artifact_manifest_approval_v1 import _package


@pytest.fixture
def package():
    binding.install_comprehensive_exact_artifact_hash_binding_v1()
    return attach_artifact_manifest(_package())


class SourceKey(str):
    """A plain dict can execute this key's equality method during get()."""

    __hash__ = str.__hash__

    def __new__(cls, name):
        key = super().__new__(cls, name)
        key.calls = 0
        return key

    def __eq__(self, other):
        self.calls += 1
        if self.calls == 2:
            self.package[self] = self.valid
        elif self.calls == 3:
            self.package[self] = self.invalid
        return super().__eq__(other)


def _invalid(field):
    return ('{"unverified":true}' if field == 'canonical_json'
            else base64.b64encode(b'%PDF-unverified').decode())


@pytest.mark.parametrize('field', ['canonical_json', 'pdf_base64'])
def test_custom_key_aba_cannot_bind_digest_to_another_source(package, field):
    valid = package.pop(field)
    key = SourceKey(field)
    key.package = package
    key.valid = valid
    key.invalid = _invalid(field)
    package[key] = key.invalid
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        binding._validate_exact_artifact_hashes(package)


class SequenceKey(str):
    __hash__ = str.__hash__

    def __new__(cls, name):
        key = super().__new__(cls, name)
        key.calls = 0
        return key

    def __eq__(self, other):
        self.calls += 1
        value = self.values[min(self.calls - 1, len(self.values) - 1)]
        self.package[self] = value
        return super().__eq__(other)


@pytest.mark.parametrize('field', ['canonical_json', 'pdf_base64'])
@pytest.mark.parametrize('replacement', ['changed', 'malformed'])
def test_later_fallback_consumes_its_single_read(package, field, replacement):
    valid = package.pop(field)
    invalid = _invalid(field)
    if replacement == 'malformed':
        invalid = '\ud800' if field == 'canonical_json' else '!'
    key = SequenceKey(field)
    key.package = package
    key.values = [valid, invalid, valid]
    package[key] = valid
    error = UnicodeEncodeError if field == 'canonical_json' and replacement == 'malformed' else ValueError
    with pytest.raises(error):
        binding._validate_exact_artifact_hashes(package)
    # The second read must not be replaced by a third fallback lookup.
    assert key.calls == 2


@pytest.mark.parametrize('field', ['canonical_json', 'pdf_base64'])
def test_equal_distinct_source_takes_fallback_and_still_validates(package, field):
    valid = package.pop(field)
    replacement = (' ' + valid)[1:]
    assert replacement == valid and replacement is not valid
    key = SequenceKey(field)
    key.package = package
    key.values = [valid, replacement]
    package[key] = valid
    binding._validate_exact_artifact_hashes(package)
    assert key.calls == 2


@pytest.mark.parametrize('subclass', [False, True])
def test_pdf_reuse_is_invocation_local_and_plain_string_only(package, monkeypatch, subclass):
    class Text(str):
        pass
    if subclass:
        package['pdf_base64'] = Text(package['pdf_base64'])
    original = binding._pdf_bytes_from_source
    decoded = []

    def observe(source):
        decoded.append(source)
        return original(source)

    monkeypatch.setattr(binding, '_pdf_bytes_from_source', observe)
    binding._validate_exact_artifact_hashes(package)
    binding._validate_exact_artifact_hashes(package)
    assert len(decoded) == (4 if subclass else 2)
    package['pdf_base64'] = _invalid('pdf_base64')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        binding._validate_exact_artifact_hashes(package)


@pytest.mark.parametrize('field', ['pdf_sha256', 'canonical_json_sha256', 'evidence_manifest_sha256'])
def test_changed_draft_identity_claim_is_not_reused(package, field):
    binding._validate_exact_artifact_hashes(package)
    package['draft_artifact_identity'][field] = '0' * 64
    with pytest.raises(ValueError, match='draft artifact identity'):
        binding._validate_exact_artifact_hashes(package)


@pytest.mark.parametrize('field', ['canonical_json', 'pdf_base64'])
def test_custom_mapping_get_preserves_single_read_contract(package, field):
    class SourceMapping(dict):
        def get(self, key, default=None):
            if key == field:
                self.reads += 1
                return self.valid if self.reads == 1 else self.invalid
            return super().get(key, default)
    source = SourceMapping(package)
    source.reads = 0
    source.valid = source[field]
    source.invalid = _invalid(field)
    with pytest.raises(ValueError):
        binding._validate_exact_artifact_hashes(source)
    assert source.reads == 2


@pytest.mark.parametrize('failure', ['lookup', 'coercion', 'decode'])
def test_pdf_failure_keeps_message_and_original_cause(package, failure):
    class BrokenLookup(dict):
        def get(self, key, default=None):
            if key == 'pdf_base64':
                raise RuntimeError('lookup failed')
            return super().get(key, default)

    class BrokenText(str):
        def __str__(self):
            raise RuntimeError('coercion failed')

    if failure == 'lookup':
        package = BrokenLookup(package)
    elif failure == 'coercion':
        package['pdf_base64'] = BrokenText(package['pdf_base64'])
    else:
        package['pdf_base64'] = '!'
    with pytest.raises(ValueError, match='^Comprehensive PDF could not be decoded for hash verification$') as caught:
        binding._validate_exact_artifact_hashes(package)
    if failure != 'decode':
        assert type(caught.value.__cause__) is RuntimeError
        assert str(caught.value.__cause__) == failure + ' failed'
    else:
        import binascii
        assert type(caught.value.__cause__) is binascii.Error


@pytest.mark.parametrize('field', ['canonical_json', 'pdf_base64'])
@pytest.mark.parametrize('read', [1, 2])
def test_ephemeral_source_is_released_at_conversion_boundary(package, field, read):
    claim = 'canonical_json_sha256' if field == 'canonical_json' else 'pdf_sha256'
    finalized = []

    class Ephemeral:
        def __str__(self):
            return source[field]

        def __del__(self):
            source[claim] = '0' * 64
            finalized.append(True)

    class EphemeralMapping(dict):
        def get(self, key, default=None):
            if key == field:
                self.calls += 1
                if self.calls == read:
                    return Ephemeral()
            return super().get(key, default)

    source = EphemeralMapping(package)
    source.calls = 0
    with pytest.raises(ValueError, match='package .* does not match retained'):
        binding._validate_exact_artifact_hashes(source)
    assert finalized == [True]
    assert source[claim] == '0' * 64
