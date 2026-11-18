"""Synthetic-only qualification on a new private local PostgreSQL cluster.

Never accepts a host, credentials, database name, SQL file, or production input.
The offline candidate's dispatch guards remain unchanged. This is not restore proof.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time

import binding
import fixed_phase_adapter as phases
import no_child_design
import offline_read_runner
import psql_pipe_adapter
import psql_owned_factory
import fixed_psql_design
import transport_bridge as bridge
import verify
from test_binding import base, NOW
from test_verifier import row, RECORD

BIN = Path('/usr/lib/postgresql/16/bin')
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'HOME': '/nonexistent'}
ROOT = Path(__file__).resolve().parent


@contextmanager
def fixture_directory():
    root = Path(tempfile.mkdtemp(prefix='nico-synthetic-pg-'))
    (root/'safe-to-remove').touch()
    try:
        yield root
    finally:
        # A failed stop must not delete a potentially running server's directory.
        if (root/'safe-to-remove').exists():
            shutil.rmtree(root)


def run(args, *, data=None, env=ENV, timeout=10, check=True):
    return subprocess.run([str(x) for x in args], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env, timeout=timeout,
                          check=check)


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def qualify():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('synthetic_github_runner_required')
    for name in ('initdb', 'pg_ctl', 'psql'):
        if not (BIN/name).is_file():
            raise ValueError('preinstalled_postgres16_required')
    checks = {}
    versions = {name: run([BIN/name, '--version']).stdout.decode().strip()
                for name in ('initdb', 'pg_ctl', 'psql')}
    hashes = {name: hashlib.sha256((BIN/name).read_bytes()).hexdigest()
              for name in ('initdb', 'pg_ctl', 'psql')}
    user = pwd.getpwuid(os.getuid()).pw_name
    if not no_child_design.IDENT.fullmatch(user):
        raise ValueError('synthetic_runner_user_invalid')
    with fixture_directory() as root:
        data, socket = root/'data', root/'socket'
        socket.mkdir(mode=0o700)
        run([BIN/'initdb', '-D', data, '-A', 'trust', '--no-locale', '--encoding=UTF8'], timeout=20)
        attempted_start = False
        try:
            # pg_ctl can launch postmaster before its wait reports a failure.
            attempted_start = True
            (root/'safe-to-remove').unlink()
            run([BIN/'pg_ctl', '-D', data, '-l', root/'server.log', '-w', '-t', '10',
                 '-o', "-k " + str(socket) + " -c listen_addresses='' -p 5432", 'start'], timeout=15)
            conninfo = (f'host={socket} port=5432 dbname=postgres user={user} '
                        f'requirepeer={user} require_auth=none passfile=/dev/null '
                        'sslmode=disable gssencmode=disable connect_timeout=5')
            command = [BIN/'psql', '-X', '-w', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1', conninfo]

            def sql(text, *, checked=True):
                return run(command, data=text.encode(), check=checked)

            expected = json.loads((ROOT/'expected-schema.json').read_text())
            tables = {k: set(v) for k, v in expected['tables'].items()}
            for name, cols in phases.SUPPLEMENTAL.items():
                tables.setdefault(name, set()).update(cols)
            for name, cols in sorted(tables.items()):
                assert phases.IDENT.fullmatch(name) and all(phases.IDENT.fullmatch(c) for c in cols)
                definitions = ','.join('"'+c+'" '+phases.READ_TYPES.get(name, {}).get(c, 'text') for c in sorted(cols))
                sql('CREATE TABLE public."'+name+'" ('+definitions+');')
            sql('INSERT INTO public.nico_schema_migrations(version,contract_sha256) VALUES ('+
                literal(expected['version'])+','+literal(expected['contract_sha256'])+');')
            selected = row()

            def seed(item):
                columns = ['run_id','customer_id','project_id','revision','integrity_sha256','status','payload']
                values = [item[k] for k in columns[:-2]] + [item['payload']['status'], json.dumps(item['payload'])]
                sql('INSERT INTO public.nico_comprehensive_runs ('+','.join(columns)+') VALUES ('+
                    ','.join(literal(v) for v in values)+');')
                sql('INSERT INTO public.nico_comprehensive_review_history_commitments VALUES ('+
                    ','.join(literal(item[k]) for k in sorted(phases.SUPPLEMENTAL[phases.EXTRA_TABLE]))+');')

            # Three lexically earlier, out-of-scope rows expose a global-LIMIT bug.
            for i in range(3):
                other = deepcopy(selected)
                other['run_id'] = other['payload']['identity']['run_id'] = f'aaa_other_{i}'
                other['customer_id'] = other['payload']['identity']['customer_id'] = 'other'
                other['payload']['integrity_sha256'] = RECORD['_record_hash'](other['payload'])
                other['integrity_sha256'] = other['payload']['integrity_sha256']
                seed(other)
            for i in range(3):
                other = deepcopy(selected)
                other['run_id'] = other['payload']['identity']['run_id'] = f'aaa_project_{i}'
                other['project_id'] = other['payload']['identity']['project_id'] = 'other'
                other['payload']['integrity_sha256'] = RECORD['_record_hash'](other['payload'])
                other['integrity_sha256'] = other['payload']['integrity_sha256']
                seed(other)
            seed(selected)
            snapshot_sql = ('SELECT md5(string_agg(row_to_json(t)::text,chr(10) ORDER BY run_id)) '
                            'FROM public.nico_comprehensive_runs t;')
            before = sql(snapshot_sql).stdout
            env = dict(ENV, PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=15000 '
                       '-c lock_timeout=1000 -c idle_in_transaction_session_timeout=30000 '
                       '-c search_path=pg_catalog -c max_parallel_workers_per_gather=0 -c jit=off')
            children = []

            def spawn_fixed(deadline):
                # Only this harness knows the newly created private socket.
                # A returned child is immediately adopted or cleaned by factory.
                child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, env=env, close_fds=True)
                children.append(child)
                return child

            def opener(digest, deadline):
                return psql_owned_factory.adopt_synthetic_fixed_child(spawn_fixed, digest, deadline)

            # Fail acquisition on the second pipe: bridge never receives ownership.
            pipe_calls = []
            def fail_second_pipe(fd, blocking):
                pipe_calls.append(fd)
                if len(pipe_calls) == 2:
                    raise ValueError('synthetic_pipe_setup_failure')
                os.set_blocking(fd, blocking)
            try:
                psql_owned_factory.adopt_synthetic_fixed_child(
                    spawn_fixed, 'a'*64, time.monotonic()+5,
                    configure_nonblocking=fail_second_pipe)
                raise AssertionError('partial_acquisition_accepted')
            except ValueError as exc:
                assert str(exc) == 'offline_fixed_factory_rejected'
            assert len(pipe_calls) == 2
            assert children[-1].poll() is not None
            assert children[-1].stdin.closed and children[-1].stdout.closed
            checks['native_partial_acquisition_reaped_and_pipes_closed'] = True

            def exercise(*, rejected=False):
                plan, observed = base()
                count = len(children)
                try:
                    answer = bridge.run_synthetic_bridge(plan, observed, opener, now=NOW,
                                                         max_age_hours=36, io_seconds=10)
                    assert not rejected
                    assert answer == {'status':'synthetic_only','sample_count':1,
                                      'database_execution_enabled':False,'restore_evidence_eligible':False}
                except ValueError as exc:
                    assert rejected and str(exc) == 'offline_transport_bridge_rejected'
                finally:
                    for child in children[count:]:
                        try:
                            assert child.poll() is not None
                            assert child.stdin.closed and child.stdout.closed
                        finally:
                            if child.poll() is None:
                                child.kill()
                            child.wait(timeout=2)
                            child.stdin.close(); child.stdout.close()
                assert sql('SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() '
                           'AND pid<>pg_backend_pid();').stdout.strip() == b'0'

            exercise()
            checks['real_psql_full_pipeline_exact_scope_before_limit'] = True
            checks['successful_session_exit_and_pipes_closed'] = True
            assert sql(snapshot_sql).stdout == before
            checks['synthetic_rows_unchanged'] = True
            denied = run(command, data=b'BEGIN READ ONLY; CREATE TABLE public.forbidden_write(x int);', env=env, check=False)
            assert denied.returncode != 0
            assert sql("SELECT to_regclass('public.forbidden_write') IS NULL;").stdout.strip() == b't'
            checks['server_rejects_write'] = True
            sql("UPDATE public.nico_schema_migrations SET contract_sha256='wrong';")
            exercise(rejected=True)
            checks['bad_ledger_rejected_and_session_closed'] = True
            sql('UPDATE public.nico_schema_migrations SET contract_sha256='+literal(expected['contract_sha256'])+';')
            sql("UPDATE public.nico_comprehensive_runs SET integrity_sha256='wrong' WHERE customer_id='synthetic';")
            exercise(rejected=True)
            checks['corrupt_record_rejected_and_session_closed'] = True
            for module in (no_child_design, offline_read_runner, phases, psql_pipe_adapter, bridge, psql_owned_factory, fixed_psql_design):
                try:
                    module.dispatch()
                    raise AssertionError('disabled_guard_changed')
                except ValueError as exc:
                    assert str(exc) == 'database_execution_disabled'
            checks['all_candidate_dispatch_guards_disabled'] = True
        finally:
            if attempted_start:
                primary_failure = sys.exc_info()[0] is not None
                try:
                    # Always attempt stop, including partially successful startup.
                    run([BIN/'pg_ctl', '-D', data, '-m', 'immediate', '-w', '-t', '10', 'stop'],
                        timeout=15, check=False)
                    assert run([BIN/'pg_ctl', '-D', data, 'status'], check=False).returncode == 3
                    (root/'safe-to-remove').touch()
                except Exception:
                    if not primary_failure:
                        raise
    checks['temporary_synthetic_cluster_removed'] = not root.exists()
    assert all(checks.values())
    return {'status':'passed','synthetic':True,'live_production_claim':False,
            'restore_evidence_eligible':False,'database_execution_enabled':False,
            'source_release':no_child_design.RELEASE,'tested_commit':os.environ.get('GITHUB_SHA'),
            'client_versions':versions,'client_sha256':hashes,'checks':checks}


if __name__ == '__main__':
    try:
        print(json.dumps(qualify(), sort_keys=True))
    except Exception:
        print(json.dumps({'status':'failed','synthetic':True,'restore_evidence_eligible':False,
                          'error':'synthetic_postgres_qualification_failed'}))
        raise SystemExit(1) from None
