"""Read-only reference from trusted server persistence, not cryptographic attestation."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json

from nico.source_function_collection_v1 import validate_collection
from nico.source_function_measurements_v1 import _json

STORE_STATE_KEY = '_source_function_conformance_store'
_CURRENT = ContextVar('source_function_witness', default=None)
_TOKEN = object()


def _binding(context: dict, repository: dict, complexity: dict) -> str:
    identity = {key: context[key] for key in ('run_id','customer_id','project_id','repository','commit_sha','evidence_ledger_id')}
    snapshot = context['prior_stage_results']['immutable_repository_snapshot']['snapshot']
    return _json({'identity':identity, 'snapshot':snapshot, 'repository':repository, 'complexity':complexity})


@dataclass(frozen=True, init=False)
class _Witness:
    binding: str

    def __init__(self, binding: str, token: object):
        if token is not _TOKEN:
            raise TypeError('witness_requires_trusted_reader')
        object.__setattr__(self, 'binding', binding)

    def matches(self, context: dict, repository: dict, complexity: dict) -> bool:
        return self.binding == _binding(context, repository, complexity)


def valid_witness(witness: object, context: dict, repository: dict, complexity: dict) -> bool:
    return type(witness) is _Witness and witness.matches(context, repository, complexity)


def load_witness(store, context: dict) -> _Witness | None:
    """Store is supplied by server wiring only; never resolve it from context."""
    from nico.comprehensive_run_record import validate_comprehensive_run_record
    from nico.comprehensive_run_store import ComprehensiveRunStore
    if not isinstance(store, ComprehensiveRunStore):
        return None

    def consume(row, restore):
        # restore() initializes absent commitments. Reject first: this reader cannot write.
        if row[1] is None or row[2] is None:
            return None
        payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        if not isinstance(payload, dict) or validate_comprehensive_run_record(payload)['status'] != 'valid':
            return None
        identity = payload['identity']
        expected = [identity[k] for k in ('run_id','customer_id','project_id','repository','commit_sha','evidence_ledger_id')]
        expected += [payload[k] for k in ('status','revision','terminal','integrity_sha256','updated_at')]
        if list(row[3:]) != expected:
            return None
        if any(context.get(k) != identity.get(k) for k in ('run_id','customer_id','project_id','repository','commit_sha','evidence_ledger_id')):
            return None
        restored = restore()  # Same row; validates review history, without legacy commitment writes.
        stage = 'repository_and_delivery_evidence'
        if stage not in restored['completed_stages']:
            return None
        stages = restored['stage_results']
        repository = stages[stage]['repository_evidence']
        complexity = stages[stage]['complexity_evidence']
        if not validate_collection(complexity):
            return None
        trusted_context = {**identity, 'prior_stage_results': stages}
        # Canonical serialization creates an immutable defensive copy. No row/closure escapes.
        return _Witness(_binding(trusted_context, repository, complexity), _TOKEN)

    try:
        return store._consume_read_snapshot(context['run_id'], consume)
    except Exception:
        # Optional read-only evidence: unavailable storage cannot grant numeric credit
        # or turn an existing report into a new acceptance failure.
        return None


def current_witness():
    return _CURRENT.get()


@contextmanager
def witness_scope(witness):
    token = _CURRENT.set(witness)
    try:
        yield
    finally:
        _CURRENT.reset(token)
