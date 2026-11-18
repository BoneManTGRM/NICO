"""Offline, fixed psql profile; never resolves, imports, or executes psql."""
from no_child_design import BEGIN_STMT, END_STMT, READY_STMT, offline_plan

# Fixed bootstrap only. Expected state must be checked and explicitly attested
# by a separately reviewed adapter before any real evidence query is added.
BOOTSTRAP_SQL = '; '.join((BEGIN_STMT, READY_STMT, END_STMT)) + ';'
EXECUTABLE = '/usr/bin/psql'

def build_fixture_argv(*, release, user, database, peer, claims):
    p=offline_plan(release=release,user=user,database=database,peer=peer,claims=claims)
    v=p['libpq_fixture_parameters']
    # Env created from scratch. No inherited PGSERVICE, PGPASSWORD, PGHOSTADDR,
    # loader, shell, HOME, auth tracing/history or operator variable snapshots.
    env={'PATH':'/usr/bin:/bin','LANG':'C','PGPASSFILE':'/dev/null',
         'PGREQUIREAUTH':'none','PGREQUIREPEER':v['requirepeer'],
         'PGSSLMODE':'disable','PGGSSENCMODE':'disable','PGCONNECT_TIMEOUT':'5',
         'PGCLIENTENCODING':'UTF8','PGOPTIONS':v['options'],
         'PSQL_PAGER':'','PAGER':'','PSQL_HISTORY':'/dev/null'}
    argv=(EXECUTABLE,'-X','-w','-q','-A','-t','-v','ON_ERROR_STOP=1',
          '-P','pager=off','-h',v['host'],'-p',v['port'],
          '-U',v['user'],'-d',v['dbname'],'-c',BOOTSTRAP_SQL)
    return {'status':'synthetic_psql_design_only','live_execution_enabled':False,
            'fixture_command':argv,'fixture_environment':env}

def dispatch():
    raise ValueError('database_execution_disabled')
