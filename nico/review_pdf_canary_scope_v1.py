"""Closed, exact retained-source canary binding; never an authorization substitute."""
from dataclasses import asdict
import json
import re

from nico.review_pdf_preparation_jobs_v1 import PreparationConflict, PreparationIdentity

FIELDS = frozenset({'customer_id', 'project_id', 'repository', 'run_id', 'commit_sha',
    'source_revision', 'source_integrity_sha256', 'canonical_truth_sha256',
    'source_artifact_sha256', 'language'})


class CanaryScope:
    def __init__(self, value):
        if type(value) is not dict or set(value) != FIELDS:
            raise ValueError('review_pdf_canary_scope_required')
        # Reuse the identity validator without binding future renderer/policy values.
        PreparationIdentity(**value, renderer_revision='0' * 40,
            policy_sha256='0' * 64, artifact_mode='pending-source-localized-draft')
        if not re.fullmatch(r'comprun_[a-zA-Z0-9_-]{1,160}', value['run_id']):
            raise ValueError('review_pdf_canary_run_invalid')
        self._values = dict(value)

    @classmethod
    def parse(cls, raw):
        if type(raw) is not str or not raw or len(raw.encode('utf-8')) > 16384:
            raise ValueError('review_pdf_canary_scope_required')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('review_pdf_canary_duplicate_field')
                result[key] = value
            return result
        return cls(json.loads(raw, object_pairs_hook=unique))

    def request(self, run_id, language, binding):
        if (run_id != self._values['run_id'] or language != self._values['language']
                or binding != {key: self._values[key] for key in
                    ('commit_sha', 'canonical_truth_sha256')}):
            raise PreparationConflict('review_pdf_outside_canary_scope')

    def check(self, identity):
        actual = asdict(identity)
        if any(actual[key] != value for key, value in self._values.items()):
            raise PreparationConflict('review_pdf_outside_canary_scope')
