"""Offline candidate. Fixed read phases only; no connector, import-time I/O or live dispatch."""
import re

RELEASE = '5eb768b5776f88bae86e972c76267915cc874c85'
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}\Z')
REQUIRED = frozenset({'isolated_socket_attested','existing_read_role_attested','sterile_runtime_attested',
                      'verified_native_library_attested','verifier_resource_limits_attested',
                      'provider_binding_attested'})
BEGIN_STMT = 'BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'
END_STMT = 'ROLLBACK'
READY_STMT = (
    "SELECT pg_catalog.current_setting('transaction_read_only'),"
    "pg_catalog.current_setting('statement_timeout'),"
    "pg_catalog.current_setting('lock_timeout'),"
    "pg_catalog.current_setting('idle_in_transaction_session_timeout'),"
    "pg_catalog.current_setting('search_path'),"
    "pg_catalog.inet_server_addr() IS NULL"
)

def check(good, code):
    if not good:
        raise ValueError(code)

def offline_plan(*, release, user, database, peer, claims):
    check(release == RELEASE,'source_release_mismatch')
    check(all(type(x) is str and IDENT.fullmatch(x) for x in (user,database,peer)),
          'socket_identity_invalid')
    check(type(claims) is dict and set(claims)==REQUIRED and all(x is True for x in claims.values()),
          'isolation_preflight_required')
    # These are fixture inputs, not assertions that the real target has these
    # settings. A real process requires a verified sterile environment first.
    args={'host':'/var/run/postgresql','port':'5432','user':user,'dbname':database,
          'requirepeer':peer,'require_auth':'none','passfile':'/dev/null',
          'sslmode':'disable','gssencmode':'disable','connect_timeout':'5',
          'options':'-c default_transaction_read_only=on -c statement_timeout=15000'
                    ' -c lock_timeout=1000 -c idle_in_transaction_session_timeout=30000'
                    ' -c search_path=pg_catalog -c max_parallel_workers_per_gather=0 -c jit=off'}
    return {'status':'synthetic_design_only','live_execution_enabled':False,
            'libpq_fixture_parameters':args,'expand_dbname':False,
            'fixed_bootstrap_statements':(BEGIN_STMT, READY_STMT, END_STMT)}

def verify_fixture_bootstrap(statement_result, *, session_status, transaction_status):
    # The role, provider route, and physical isolation are NOT learned by SQL.
    # Values below are synthetic text results matching the deployment profile.
    expected=('on','15s','1s','30s','pg_catalog',True)
    check(type(statement_result) is tuple and len(statement_result)==len(expected),
          'fixture_session_shape_invalid')
    check(all(type(actual) is type(wanted) and actual==wanted
              for actual,wanted in zip(statement_result,expected)) and
          session_status=='ok' and transaction_status=='in_read_transaction',
          'fixture_session_state_invalid')
    return {'status':'synthetic_only','live_execution_enabled':False,
            'restore_evidence_eligible':False}

def dispatch():
    raise ValueError('database_execution_disabled')
