#!/bin/bash
set -euo pipefail
# A unique local-only CI marker; this is never a deployed Railway service.
test "${NICO_CI_FIXTURE_MODE:-}" = github-synthetic-no-network
test -z "${RAILWAY_SERVICE_ID:-}"
test "$(id -u)" = 0
umask 077
root=/tmp/nico-native-fixture
# Never adopt/reuse a preexisting data directory.
mkdir "$root"
chown postgres:postgres "$root"
chmod 0711 "$root"
pg() { env -i PATH=/usr/lib/postgresql/18/bin:/usr/local/bin:/usr/bin:/bin HOME=/tmp PGHOST="$root/socket" PGPORT=6543 PGUSER=postgres PGDATABASE=postgres PGPASSFILE=/dev/null PGCONNECT_TIMEOUT=5 gosu postgres "$@"; }
cleanup() {
  rc=$?; trap - EXIT TERM INT; ok=1
  for cluster in target source; do
    if test -s "$root/$cluster/postmaster.pid"; then
      pg pg_ctl -D "$root/$cluster" -m fast -w -t 12 stop >/dev/null 2>&1 || ok=0
    fi
  done
  if test "$ok" = 1; then rm -rf -- "$root"; else echo SYNTHETIC_CLEANUP_FAILED; exit 1; fi
  test ! -e "$root" || exit 1
  if test "$rc" = 0; then echo SYNTHETIC_CLEANUP_OK; fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 143' TERM INT
install -d -m 711 -o postgres -g postgres "$root/socket"
boot() {
  pg initdb -D "$root/$1" --encoding=UTF8 --locale=C --auth-local=peer --auth-host=reject >/dev/null
  if test "$1" = target; then
    printf 'fixture_reader_map nobody fixture_reader\n' >> "$root/target/pg_ident.conf"
    printf 'local nico_fixture_recovered fixture_reader peer map=fixture_reader_map\nlocal all postgres peer\nlocal all all reject\nhost all all 0.0.0.0/0 reject\nhost all all ::/0 reject\n' > "$root/target/pg_hba.conf"
    chown postgres:postgres "$root/target/pg_ident.conf" "$root/target/pg_hba.conf"
  fi
  pg pg_ctl -D "$root/$1" -o "-c listen_addresses= -k $root/socket -p 6543" -l "$root/$1.log" -w -t 18 start >/dev/null
  test "$(pg psql -X -w -qAt -c 'SHOW server_version_num')" = 180007
}
py() { local os_user=postgres; if test "$1" = read; then os_user=nobody; fi; env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 NICO_SYNTHETIC_JOB=pg18-native-v1 PYTHONHOME=/opt/nico-python LD_LIBRARY_PATH=/opt/nico-python/lib gosu "$os_user" /opt/nico-python/bin/python3 /opt/nico-reader/synthetic_fixture.py "$@"; }
boot source
pg createdb nico_fixture
py seed
pg psql -X -w -v ON_ERROR_STOP=1 -qAt -d nico_fixture <<'SQL'
CREATE TABLE nico_synthetic_padding AS SELECT i, md5(i::text) AS payload FROM generate_series(1,120000) AS g(i);
SQL
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=NICO synthetic CI only' \
  -keyout "$root/recv.key" -out "$root/recv.cert" >/dev/null 2>&1
openssl genpkey -algorithm ED25519 -out "$root/sender.key" >/dev/null 2>&1
openssl pkey -in "$root/sender.key" -pubout -out "$root/sender.pub" >/dev/null 2>&1
pg pg_dump -w --no-owner --no-acl -Fc nico_fixture |
  env -i PATH=/usr/bin:/bin NICO_FRAME_TEST_ONLY=fixed-local-synthetic \
    /bin/bash /opt/nico-reader/stream_frame.sh "$root/recv.cert" "$root/sender.key" "$root/sealed" 418a577fea014da581954380304aaaaa
test -f "$root/sealed/part-0001.cms"
py after-backup
pg pg_ctl -D "$root/source" -m fast -w -t 12 stop >/dev/null
boot target
stream() { env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 NICO_CI_FIXTURE_MODE=github-synthetic-no-network PYTHONHOME=/opt/nico-python LD_LIBRARY_PATH=/opt/nico-python/lib /opt/nico-python/bin/python3 /opt/nico-reader/stream_restore.py "$@"; }
pg createdb nico_fixture_recovered
stream pass
test "$(pg psql -X -w -qAt -d nico_fixture_recovered -c 'SELECT count(*) FROM nico_synthetic_padding')" = 120000
pg createdb nico_fixture_failed
stream mutate
test "$(pg psql -X -w -qAt -d nico_fixture_failed -c "SELECT to_regclass('public.nico_synthetic_padding') IS NULL")" = t
pg dropdb -w nico_fixture_failed
echo SYNTHETIC_FAILED_TARGET_DISCARDED
pg psql -X -w -v ON_ERROR_STOP=1 -qAt -d nico_fixture_recovered <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE nico_fixture_recovered FROM PUBLIC;
CREATE ROLE fixture_reader LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT CONNECT ON DATABASE nico_fixture_recovered TO fixture_reader;
GRANT USAGE ON SCHEMA public TO fixture_reader;
GRANT SELECT ON public.nico_comprehensive_runs,public.nico_comprehensive_review_history_commitments TO fixture_reader;
SQL
test "$(pg psql -X -w -qAt -d nico_fixture_recovered -c "SELECT count(*) FROM public.nico_comprehensive_runs WHERE run_id='comprun_after_backup'")" = 0
py read
test ! -e "$root/fixture.dump"
echo "SYNTHETIC_NO_PLAINTEXT_ARCHIVE_FILE"
