#!/bin/bash
# Synthetic PG18.6 fixture. Only the isolated, reviewed GitHub CI runtime.
set -euo pipefail

accept_negative() {
 local psql_rc=$1 psql_error=$2 dump_rc=$3 dump_error=$4
 [[ $psql_rc = 3 && $dump_rc =~ ^[1-9][0-9]*$ && $dump_rc -lt 124 ]] &&
 grep -Eq '^ERROR: +0A000: cannot import a snapshot from a different database$' "$psql_error" &&
 grep -Fq 'cannot import a snapshot from a different database' "$dump_error"
}

qualify() {
 [[ ${1:-} = --approved-synthetic-only && $# = 1 ]]
 [[ ${NICO_CI_FIXTURE_MODE:-} = github-synthetic-no-network ]]
 [[ -z ${RAILWAY_PROJECT_ID:-} && -z ${RAILWAY_ENVIRONMENT_ID:-} && -z ${RAILWAY_SERVICE_ID:-} ]]
 [[ $(id -u) = 0 ]]
 umask 077
 rt=$(mktemp -d /tmp/nico-snapshot-fake.XXXXXXXX)
 readonly rt
 stage=setup completed=0 cp= a_bytes= b_bytes=
 pg() { env -i PATH=/usr/lib/postgresql/18/bin:/usr/local/bin:/usr/bin:/bin LC_ALL=C HOME=/nonexistent PGHOST="$rt/socket" PGPORT=6543 PGUSER="$1" PGPASSFILE=/dev/null PGCONNECT_TIMEOUT=3 gosu postgres "${@:2}"; }
 admin() { pg postgres psql -w -XqAt -v ON_ERROR_STOP=1 "$@"; }
 reader() { pg snapshot_fixture psql -w -XqAt -v ON_ERROR_STOP=1 -v VERBOSITY=verbose "$@"; }
 owned_stop() {
  if [[ -s $rt/cluster/postmaster.pid ]]; then
   pg postgres pg_ctl -D "$rt/cluster" -m fast -w -t 10 stop >"$rt/stop.out" 2>&1 &&
     [[ ! -e $rt/cluster/postmaster.pid ]]
  fi
 }
 cleanup() {
  local rc=$?
  trap - EXIT
  trap '' TERM INT
  exec 7>&-
  if [[ -n $cp ]]; then kill -TERM "$cp" 2>/dev/null || :; fi
  if ! owned_stop; then echo SYNTHETIC_SNAPSHOT_STOP_UNVERIFIED; exit 1; fi
  if [[ -n $cp ]]; then wait "$cp" 2>/dev/null || :; fi
  rm -rf -- "$rt"
  [[ ! -e $rt ]] || exit 1
  if [[ $rc = 0 && $completed = 1 ]]; then
   printf 'SYNTHETIC_SNAPSHOT_PASS own_db_positive=2 wrong_db_sqlstate=0A000 wrong_db_dump_rejected=2 discarded_private_bytes_a_to_b=%s discarded_private_bytes_b_to_a=%s published=false cleanup_verified=true gate_eligible=false\n' "$a_bytes" "$b_bytes"
   exit 0
  fi
  printf 'SYNTHETIC_SNAPSHOT_FAILED stage=%s published=false cleanup_verified=true\n' "$stage" >&2
  exit 1
 }
 trap cleanup EXIT
 trap 'exit 143' TERM INT
 chown postgres:postgres "$rt"
 chmod 0711 "$rt" # socket access only; all non-socket entries below remain private.
 install -d -m 0700 -o postgres -g postgres "$rt/socket"
 cd "$rt"
 (
  pg postgres initdb -D "$rt/cluster" -U postgres --encoding=UTF8 --locale=C --auth-local=peer --auth-host=reject
  printf '%s\n' 'snapshot_fixture_map postgres snapshot_fixture' > "$rt/cluster/pg_ident.conf"
  cat > "$rt/cluster/pg_hba.conf" <<'HBA'
local snapshot_fake_a,snapshot_fake_b snapshot_fixture peer map=snapshot_fixture_map
local all postgres peer
local all all reject
host all all 0.0.0.0/0 reject
host all all ::/0 reject
HBA
  pg postgres pg_ctl -D "$rt/cluster" -o "-c listen_addresses= -k $rt/socket -p 6543 -c max_connections=8 -c log_statement=none" -l "$rt/server.log" -w -t 15 start
  [[ $(admin -d postgres -c 'SHOW server_version_num') = 180006 ]]
  [[ -z $(admin -d postgres -c 'SHOW listen_addresses') ]]
  [[ $(pg postgres pg_dump --version) = 'pg_dump (PostgreSQL) 18.6'* ]]
  [[ $(admin -d postgres -c 'SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL') = 0 ]]
  admin -d postgres -c 'CREATE ROLE snapshot_fixture LOGIN PASSWORD NULL NOINHERIT NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS'
  for db in snapshot_fake_a snapshot_fake_b; do
   pg postgres createdb -w "$db"
   admin -d "$db" -c "REVOKE ALL ON DATABASE $db FROM PUBLIC; GRANT CONNECT ON DATABASE $db TO snapshot_fixture; CREATE TABLE public.fake_t(id integer PRIMARY KEY); INSERT INTO public.fake_t VALUES (42); REVOKE ALL ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO snapshot_fixture; GRANT SELECT ON public.fake_t TO snapshot_fixture"
   [[ $(reader -d "$db" -c 'SELECT current_user,inet_client_addr() IS NULL,count(*) FROM public.fake_t') = 'snapshot_fixture|t|1' ]]
  done
  [[ $(admin -d postgres -c "SELECT count(DISTINCT oid) FROM pg_database WHERE datname IN ('snapshot_fake_a','snapshot_fake_b')") = 2 ]]
 ) >"$rt/setup.log" 2>&1
 local from to token psql_rc dump_rc i
 for from in snapshot_fake_a snapshot_fake_b; do
  if [[ $from = snapshot_fake_a ]]; then to=snapshot_fake_b; else to=snapshot_fake_a; fi
  stage=coordinator
  mkfifo "$rt/$from.fifo"
  exec 7<>"$rt/$from.fifo"
  timeout --signal=TERM --kill-after=2s 25s env -i PATH=/usr/lib/postgresql/18/bin:/usr/local/bin:/usr/bin:/bin LC_ALL=C HOME=/nonexistent PGHOST="$rt/socket" PGPORT=6543 PGUSER=snapshot_fixture PGPASSFILE=/dev/null PGCONNECT_TIMEOUT=3 PGAPPNAME=synthetic_snapshot_coord gosu postgres psql -w -XqAt -v ON_ERROR_STOP=1 -d "$from" <"$rt/$from.fifo" >"$rt/$from.token" 2>"$rt/$from.coord-error" 7>&- & cp=$!
  printf '%s\n' 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;' 'SELECT pg_export_snapshot();' >&7
  token=
  for ((i=0;i<50;i++)); do
   if read -r token <"$rt/$from.token"; then break; fi
   sleep .1
  done
  [[ $token =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9]+$ ]]
  stage=own_db_dump
  pg snapshot_fixture pg_dump -w -Fc --no-owner --no-acl --snapshot="$token" "$from" >"$rt/$from.positive" 2>"$rt/$from.positive-error"
  [[ -s $rt/$from.positive ]]
  pg postgres pg_restore -l <"$rt/$from.positive" >"$rt/$from.toc" 2>"$rt/$from.toc-error"
  grep -Eq 'TABLE DATA public fake_t' "$rt/$from.toc"
  stage=cross_db_negative
  psql_rc=0; dump_rc=0
  printf "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSET TRANSACTION SNAPSHOT '%s';\n" "$token" |
      reader -d "$to" >"$rt/$from.cross-psql" 2>"$rt/$from.cross-psql-error" || psql_rc=$?
  pg snapshot_fixture pg_dump -w -Fc --no-owner --no-acl --snapshot="$token" "$to" >"$rt/$from.cross-dump" 2>"$rt/$from.cross-dump-error" || dump_rc=$?
  accept_negative "$psql_rc" "$rt/$from.cross-psql-error" "$dump_rc" "$rt/$from.cross-dump-error"
  if [[ $from = snapshot_fake_a ]]; then a_bytes=$(wc -c <"$rt/$from.cross-dump"); else b_bytes=$(wc -c <"$rt/$from.cross-dump"); fi
  stage=coordinator_close
  printf '%s\n' 'ROLLBACK;' '\q' >&7
  exec 7>&-
  wait "$cp"; cp=
  [[ $(admin -d postgres -c "SELECT count(*) FROM pg_stat_activity WHERE application_name='synthetic_snapshot_coord'") = 0 ]]
 done
 completed=1
}

if [[ ${BASH_SOURCE[0]} = "$0" ]]; then
 # All real execution from explicit qualified scope, within 90s+15s stop budget.
 exec timeout --signal=TERM --kill-after=15s 90s /bin/bash -c 'source "$1"; shift; qualify "$@"' bash "$0" "$@"
fi
