"""Offline assertions only. Does not attest provider facts or execute a database."""
from datetime import datetime, timedelta, timezone
import re
import hashlib
import json

RELEASE = '5eb768b5776f88bae86e972c76267915cc874c85'
IDENTIFIERS = ('project', 'environment', 'service', 'deployment', 'volume')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
SCOPE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z')
ATTESTATIONS = ('provider_target_identity', 'provider_exact_restore_lineage', 'network_isolation',
                'no_client_routing', 'no_production_write_authority', 'dedicated_target_volume',
                'cost_and_cleanup_approval', 'permitted_transfer_and_execution')
OBSERVED_KEYS = frozenset(('project', 'environment', 'service', 'deployment', 'volume'))

def require(good, code):
    if not good:
        raise ValueError(code)

def time(value):
    require(isinstance(value, str) and TIMESTAMP.fullmatch(value), 'timestamp_invalid')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('timestamp_invalid') from None

def validate_read_scope(scope):
    # Scope syntax is intentionally narrower than arbitrary SQL text. This
    # validates a reviewed receipt's structure, never attests its provenance.
    require(type(scope) is dict and set(scope)=={'customer_id','project_id','receipt_sha256'},
            'read_scope_missing')
    for k in ('customer_id','project_id'):
        v=scope[k]
        require(type(v) is str and SCOPE_ID.fullmatch(v) is not None and
                v.casefold() not in ('all','any','unbound'),'read_scope_invalid')
    receipt=scope['receipt_sha256']
    require(type(receipt) is str and DIGEST.fullmatch(receipt) and receipt!='0'*64,
            'read_scope_receipt_invalid')
    return scope['customer_id'], scope['project_id']

def validate_binding(plan, observed, *, now, max_age_hours):
    require(isinstance(plan, dict), 'binding_unbound')
    require(set(plan) == {'release', 'production', 'target', 'backup_reference_sha256', 'restored_backup_reference_sha256',
                         'backup_completed_utc', 'pitr_target_utc', 'restore_completed_utc', 'verified_utc', 'receipts', 'approved_read_scope'}, 'binding_shape_invalid')
    require(plan['release'] == RELEASE, 'release_mismatch')
    validate_read_scope(plan['approved_read_scope'])
    prod, target = plan['production'], plan['target']
    for identity in (prod, target, observed):
        require(isinstance(identity, dict) and set(identity) == OBSERVED_KEYS, 'identity_missing')
        require(all(isinstance(x, str) and UUID.fullmatch(x) and x != '00000000-0000-0000-0000-000000000000'
                    for x in identity.values()), 'identity_invalid')
        require(len(set(identity.values())) == len(IDENTIFIERS), 'identity_invalid')
    require(observed == target, 'runtime_target_mismatch')
    # Project/environment are placement labels. Operational isolation is
    # established only by independently reviewed receipts; names cannot prove
    # or disprove it. The live service, deployment, and volume may never recur.
    require(set(prod.values()).isdisjoint(target[key] for key in ('service','deployment','volume')),
            'production_boundary_collision')
    require(target['project'] not in (prod[key] for key in IDENTIFIERS[1:]),
            'production_boundary_collision')
    require(target['environment'] not in (prod[key] for key in ('project','service','deployment','volume')),
            'production_boundary_collision')
    require(target['environment'] != prod['environment'] or target['project'] == prod['project'],
            'production_boundary_collision')
    for name in ('backup_reference_sha256', 'restored_backup_reference_sha256'):
        x = plan[name]
        require(isinstance(x,str) and DIGEST.fullmatch(x) and x != '0'*64, 'backup_reference_invalid')
    require(plan['backup_reference_sha256'] == plan['restored_backup_reference_sha256'], 'restore_lineage_mismatch')
    require(isinstance(now,datetime) and now.tzinfo == timezone.utc and type(max_age_hours) is int
            and 1 <= max_age_hours <= 168, 'current_policy_unverified')
    backup, pitr, restored, verified = (time(plan[key]) for key in
        ('backup_completed_utc', 'pitr_target_utc', 'restore_completed_utc', 'verified_utc'))
    require(backup <= pitr <= restored <= verified <= now, 'chronology_invalid')
    require(now-backup <= timedelta(hours=max_age_hours), 'backup_stale')
    require(now-verified <= timedelta(minutes=30), 'target_verification_stale')
    receipts=plan['receipts']
    require(isinstance(receipts,dict) and set(receipts)==set(ATTESTATIONS), 'attestation_missing')
    require(all(isinstance(x,str) and DIGEST.fullmatch(x) and x != '0'*64
                for x in receipts.values()), 'attestation_invalid')
    # Receipt hashes identify a reviewed record; they do not independently verify it.
    return {'status':'offline_checks_passed', 'database_execution_enabled':False,
            'provider_attestations_verified_by_program':False, 'release':RELEASE}

def derive_synthetic_transport_binding(plan, observed, *, now, max_age_hours):
    # Not an authorization token or provider receipt. Values stay in memory.
    validate_binding(plan, observed, now=now, max_age_hours=max_age_hours)
    packet={'domain':'nico-offline-synthetic-transport-v2','plan':plan,
            'observed':observed,'max_age_hours':max_age_hours}
    return hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':')).encode()).hexdigest()

if __name__ == '__main__':
    print('{"status":"blocked","code":"target_unbound_database_execution_disabled"}')
    raise SystemExit(1)
