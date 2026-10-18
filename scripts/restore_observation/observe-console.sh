set +x
: "${POSTGRES_USER:?local_user_binding_missing}" "${POSTGRES_DB:?local_database_binding_missing}"
: "${NICO_EXPECTED_RUN_ID:?nonsecret_exact_run_id_required}"
if timeout --kill-after=5s 90s env -i PATH="$PATH" \
 PGHOST=/var/run/postgresql PGPORT=5432 \
 PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" \
 PGPASSFILE=/dev/null PGREQUIREAUTH=none PGCONNECT_TIMEOUT=5 \
 PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000' \
 psql -X -w -qAt -d 'require_auth=none passfile=/dev/null' -v ON_ERROR_STOP=1 -v expected_run_id="$NICO_EXPECTED_RUN_ID" 2>/dev/null <<'READ_ONLY_SQL'
-- REVIEW CANDIDATE ONLY. No live execution performed.
-- Source: BoneManTGRM/NICO @ 1ec27874c8661d5a2497929fc06bdda47e70d856.
-- Requires a separately confirmed, non-secret psql expected_run_id variable.
-- Use only the previously reviewed clean-environment local-socket/auth-none
-- wrapper, -X -w ON_ERROR_STOP, 90s external watchdog, and transaction-closed
-- marker. No bootstrap, function installation, extension, writes or retries.
-- This observes stored metadata and a bound browser report manifest. It does
-- NOT decompress canonical data, recompute Python canonical hashes, or verify
-- report bytes. Hash format/equality checks are not content-integrity checks.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = 3000;
SET LOCAL lock_timeout = 1000;
SET LOCAL idle_in_transaction_session_timeout = 10000;
SET LOCAL search_path = pg_catalog;
WITH required(table_name,column_name,contract_group) AS (VALUES
  ('customers','customer_id','contract'),
  ('customers','name','contract'),
  ('customers','created_at','contract'),
  ('projects','project_id','contract'),
  ('projects','customer_id','contract'),
  ('projects','name','contract'),
  ('projects','created_at','contract'),
  ('authorized_repositories','repository_id','contract'),
  ('authorized_repositories','customer_id','contract'),
  ('authorized_repositories','project_id','contract'),
  ('authorized_repositories','repository','contract'),
  ('authorized_repositories','authorization_scope','contract'),
  ('authorized_repositories','created_at','contract'),
  ('assessment_runs','run_id','contract'),
  ('assessment_runs','customer_id','contract'),
  ('assessment_runs','project_id','contract'),
  ('assessment_runs','workflow','contract'),
  ('assessment_runs','status','contract'),
  ('assessment_runs','payload','contract'),
  ('assessment_runs','risk_trend','contract'),
  ('assessment_runs','dependency_trend','contract'),
  ('assessment_runs','ci_reliability_trend','contract'),
  ('assessment_runs','qa_readiness_trend','contract'),
  ('assessment_runs','backlog_health_trend','contract'),
  ('assessment_runs','created_at','contract'),
  ('scanner_runs','scan_id','contract'),
  ('scanner_runs','customer_id','contract'),
  ('scanner_runs','project_id','contract'),
  ('scanner_runs','status','contract'),
  ('scanner_runs','payload','contract'),
  ('scanner_runs','created_at','contract'),
  ('scanner_runs','updated_at','contract'),
  ('scanner_raw_artifacts','artifact_id','contract'),
  ('scanner_raw_artifacts','run_id','contract'),
  ('scanner_raw_artifacts','scan_id','contract'),
  ('scanner_raw_artifacts','customer_id','contract'),
  ('scanner_raw_artifacts','project_id','contract'),
  ('scanner_raw_artifacts','repository','contract'),
  ('scanner_raw_artifacts','commit_sha','contract'),
  ('scanner_raw_artifacts','scanner_name','contract'),
  ('scanner_raw_artifacts','raw_sha256','contract'),
  ('scanner_raw_artifacts','gzip_sha256','contract'),
  ('scanner_raw_artifacts','gzip_blob','contract'),
  ('scanner_raw_artifacts','created_at','contract'),
  ('evidence_items','evidence_id','contract'),
  ('evidence_items','customer_id','contract'),
  ('evidence_items','project_id','contract'),
  ('evidence_items','run_id','contract'),
  ('evidence_items','filename','contract'),
  ('evidence_items','content_type','contract'),
  ('evidence_items','size_bytes','contract'),
  ('evidence_items','metadata','contract'),
  ('evidence_items','created_at','contract'),
  ('reports','report_id','contract'),
  ('reports','customer_id','contract'),
  ('reports','project_id','contract'),
  ('reports','run_id','contract'),
  ('reports','format','contract'),
  ('reports','payload','contract'),
  ('reports','created_at','contract'),
  ('client_jobs','job_id','contract'),
  ('client_jobs','customer_id','contract'),
  ('client_jobs','project_id','contract'),
  ('client_jobs','status','contract'),
  ('client_jobs','payload','contract'),
  ('client_jobs','created_at','contract'),
  ('client_jobs','updated_at','contract'),
  ('client_job_exports','export_id','contract'),
  ('client_job_exports','job_id','contract'),
  ('client_job_exports','customer_id','contract'),
  ('client_job_exports','project_id','contract'),
  ('client_job_exports','format','contract'),
  ('client_job_exports','payload','contract'),
  ('client_job_exports','created_at','contract'),
  ('approval_queue_items','approval_id','contract'),
  ('approval_queue_items','customer_id','contract'),
  ('approval_queue_items','project_id','contract'),
  ('approval_queue_items','status','contract'),
  ('approval_queue_items','payload','contract'),
  ('approval_queue_items','created_at','contract'),
  ('approval_queue_items','updated_at','contract'),
  ('draft_pr_records','draft_pr_id','contract'),
  ('draft_pr_records','customer_id','contract'),
  ('draft_pr_records','project_id','contract'),
  ('draft_pr_records','approval_id','contract'),
  ('draft_pr_records','status','contract'),
  ('draft_pr_records','payload','contract'),
  ('draft_pr_records','created_at','contract'),
  ('audit_log','audit_id','contract'),
  ('audit_log','customer_id','contract'),
  ('audit_log','project_id','contract'),
  ('audit_log','action','contract'),
  ('audit_log','payload','contract'),
  ('audit_log','created_at','contract'),
  ('nico_schema_migrations','version','contract'),
  ('nico_schema_migrations','contract_sha256','contract'),
  ('nico_schema_migrations','applied_at','contract'),
  ('nico_schema_migrations','verified_at','contract'),
  ('nico_comprehensive_runs','run_id','comprehensive'),
  ('nico_comprehensive_runs','customer_id','comprehensive'),
  ('nico_comprehensive_runs','project_id','comprehensive'),
  ('nico_comprehensive_runs','repository','comprehensive'),
  ('nico_comprehensive_runs','commit_sha','comprehensive'),
  ('nico_comprehensive_runs','evidence_ledger_id','comprehensive'),
  ('nico_comprehensive_runs','status','comprehensive'),
  ('nico_comprehensive_runs','revision','comprehensive'),
  ('nico_comprehensive_runs','terminal','comprehensive'),
  ('nico_comprehensive_runs','integrity_sha256','comprehensive'),
  ('nico_comprehensive_runs','updated_at','comprehensive'),
  ('nico_comprehensive_runs','payload','comprehensive'),
  ('nico_comprehensive_browser_projections','run_id','comprehensive'),
  ('nico_comprehensive_browser_projections','revision','comprehensive'),
  ('nico_comprehensive_browser_projections','run_integrity_sha256','comprehensive'),
  ('nico_comprehensive_browser_projections','projection_sha256','comprehensive'),
  ('nico_comprehensive_browser_projections','updated_at','comprehensive'),
  ('nico_comprehensive_browser_projections','projection','comprehensive')
), missing AS (
 SELECT r.* FROM required AS r LEFT JOIN information_schema.columns AS c
 ON c.table_schema='public' AND c.table_name=r.table_name AND c.column_name=r.column_name
 WHERE c.column_name IS NULL
)
SELECT count(*)=0 AS columns_ok,
 coalesce(sum(CASE WHEN contract_group='contract' THEN 1 ELSE 0 END),0) AS contract_missing_columns,
 coalesce(sum(CASE WHEN contract_group='comprehensive' THEN 1 ELSE 0 END),0) AS comprehensive_missing_columns
FROM missing
\gset
\if :columns_ok
WITH ledger AS MATERIALIZED (
 SELECT contract_sha256 = '8ab54b42689aa75fdb3bd40ca4582491eaf585ac6a7c73117cb7d9d200d5e534' AS matches
 FROM public.nico_schema_migrations WHERE version='2026.09.08.1' LIMIT 2
), ledger_check AS (
 SELECT count(*)=1 AND coalesce(bool_and(matches),false) AS ledger_valid FROM ledger
), runs AS MATERIALIZED (
  SELECT run_id, customer_id, project_id, repository, commit_sha,
         evidence_ledger_id, status, revision, terminal, integrity_sha256,
         updated_at, payload
  FROM public.nico_comprehensive_runs
  WHERE run_id = :'expected_run_id'
  LIMIT 2
), joined AS MATERIALIZED (
  SELECT r.*, p.revision AS projection_revision,
         p.run_integrity_sha256, p.projection_sha256,
         p.updated_at AS projection_updated_at, p.projection,
         r.payload -> '__nico_comprehensive_run_storage_v1__' AS envelope
  FROM runs AS r
  LEFT JOIN LATERAL (
    SELECT revision, run_integrity_sha256, projection_sha256, updated_at, projection
    FROM public.nico_comprehensive_browser_projections AS p
    WHERE p.run_id = r.run_id
    LIMIT 2
  ) AS p ON true
), checks AS MATERIALIZED (
  SELECT *,
    coalesce(
      current_setting('transaction_read_only') = 'on'
      AND current_setting('transaction_isolation') = 'repeatable read'
      AND run_id ~ '^[A-Za-z0-9_-]{1,128}$' AND length(run_id) BETWEEN 1 AND 128 AND octet_length(run_id) <= 1024
      AND length(customer_id) BETWEEN 1 AND 256 AND octet_length(customer_id) <= 1024
      AND length(project_id) BETWEEN 1 AND 256 AND octet_length(project_id) <= 1024
      AND length(repository) BETWEEN 1 AND 256 AND octet_length(repository) <= 1024
      AND length(evidence_ledger_id) BETWEEN 1 AND 256 AND octet_length(evidence_ledger_id) <= 1024
      AND commit_sha ~ '^[0-9a-f]{40}$'
      AND integrity_sha256 ~ '^[0-9a-f]{64}$'
      AND status IN ('review_required','approved','rejected','failed','blocked','queued','running','pending','planned','in_progress')
      AND length(commit_sha)=40 AND length(integrity_sha256)=64
      AND length(updated_at) BETWEEN 1 AND 64
      AND revision >= 0 AND terminal IS TRUE
      AND jsonb_typeof(payload) = 'object', false) AS run_metadata_valid,
    coalesce(
      jsonb_typeof(projection) = 'object'
      AND projection_revision = revision
      AND run_integrity_sha256 = integrity_sha256
      AND projection_sha256 ~ '^[0-9a-f]{64}$' AND length(projection_sha256)=64
      AND length(projection_updated_at) BETWEEN 1 AND 64
      AND projection -> 'run_id' = to_jsonb(run_id)
      AND projection -> 'customer_id' = to_jsonb(customer_id)
      AND projection -> 'project_id' = to_jsonb(project_id)
      AND projection -> 'repository' = to_jsonb(repository)
      AND projection -> 'commit_sha' = to_jsonb(commit_sha)
      AND projection -> 'evidence_ledger_id' = to_jsonb(evidence_ledger_id)
      AND projection -> 'revision' = to_jsonb(revision)
      AND projection -> 'integrity_sha256' = to_jsonb(integrity_sha256)
      AND projection -> 'canonical_status' = to_jsonb(status)
      AND projection -> 'terminal' = to_jsonb(terminal)
      AND projection #> '{response_projection,browser_projection}' = 'true'::jsonb
      AND projection #> '{response_projection,durable_projection}' = 'true'::jsonb,
      false) AS projection_metadata_bound,
    coalesce(
      jsonb_typeof(projection -> 'reports') = 'object'
      AND projection #> '{reports,pdf_available}' = 'true'::jsonb
      AND projection #> '{reports,json_available}' = 'true'::jsonb
      AND projection #> '{response_projection,terminal_report_manifest_attached}' = 'true'::jsonb
      AND left(projection #>> '{reports,pdf_sha256}',65) ~ '^[0-9a-f]{64}$'
      AND left(projection #>> '{reports,canonical_truth_sha256}',65) ~ '^[0-9a-f]{64}$',
      false) AS stored_report_manifest_present,
    CASE WHEN payload ? '__nico_comprehensive_run_storage_v1__' THEN
      coalesce(
        jsonb_typeof(envelope) = 'object'
        AND payload - '__nico_comprehensive_run_storage_v1__' = '{}'::jsonb
        AND envelope ?& ARRAY['schema','encoding','size_bytes','sha256','data']
        AND envelope - ARRAY['schema','encoding','size_bytes','sha256','data'] = '{}'::jsonb
        AND ((envelope ->> 'schema' = 'nico.comprehensive_run_storage.v1'
              AND envelope ->> 'encoding' = 'zlib+base64')
          OR (envelope ->> 'schema' = 'nico.comprehensive_run_storage.v2'
              AND envelope ->> 'encoding' = 'zlib+json-token-refs-v1+base64')
          OR (envelope ->> 'schema' = 'nico.comprehensive_run_storage.v3'
              AND envelope ->> 'encoding' = 'zlib+json-chunk-refs-v1+base64'))
        AND jsonb_typeof(envelope -> 'size_bytes') = 'number'
        AND left(envelope ->> 'size_bytes',12) ~ '^[0-9]{1,10}$'
        AND envelope -> 'size_bytes' > '0'::jsonb
        AND envelope -> 'size_bytes' <= '1073741824'::jsonb
        AND left(envelope ->> 'sha256',65) ~ '^[0-9a-f]{64}$'
        AND jsonb_typeof(envelope -> 'data') = 'string'
        AND octet_length(envelope ->> 'data') BETWEEN 1 AND 178956972, false)
    ELSE coalesce(
      jsonb_typeof(payload -> 'identity') = 'object'
      AND payload #> '{identity,run_id}' = to_jsonb(run_id)
      AND payload -> 'integrity_sha256' = to_jsonb(integrity_sha256), false)
    END AS storage_metadata_shape_valid
  FROM joined
), summary AS (
  SELECT (SELECT count(*) FROM runs) AS run_count,
         count(*) AS joined_row_count,
         coalesce(bool_and(run_metadata_valid),false) AS run_metadata_valid,
         coalesce(bool_and(projection_metadata_bound),false) AS projection_metadata_bound,
         coalesce(bool_and(stored_report_manifest_present),false) AS stored_report_manifest_present,
         coalesce(bool_and(storage_metadata_shape_valid),false) AS storage_metadata_shape_valid,
         coalesce(bool_or(payload ? '__nico_comprehensive_run_storage_v1__'),false) AS compressed_envelope_present,
         encode(sha256(convert_to(coalesce(jsonb_agg(jsonb_build_array(
           left(run_id,129), left(customer_id,257), left(project_id,257),
           left(repository,257), left(commit_sha,41), left(evidence_ledger_id,257),
           left(status,32), revision, terminal, left(updated_at,65),
           left(projection_updated_at,65), left(integrity_sha256,65),
           left(projection_sha256,65),
           left(projection #>> '{reports,pdf_sha256}',65),
           left(projection #>> '{reports,canonical_truth_sha256}',65),
           left(envelope ->> 'sha256',65)
         ))::text,'null'),'UTF8')),'hex') AS observation_sha256
  FROM checks
)
SELECT jsonb_build_object(
  'status', CASE WHEN ledger_valid AND run_count=1 AND joined_row_count=1 AND run_metadata_valid
                    AND projection_metadata_bound AND stored_report_manifest_present
                    AND storage_metadata_shape_valid
               THEN 'bounded_comprehensive_metadata_observation' ELSE 'blocked' END,
  'scope','exact_run_canonical_row_and_stored_browser_manifest_metadata_v2',
  'required_contract_columns_verified',true, 'comprehensive_columns_verified',true,
  'schema_contract_sha256','8ab54b42689aa75fdb3bd40ca4582491eaf585ac6a7c73117cb7d9d200d5e534',
  'migration_ledger_matches',ledger_valid,
  'run_count',run_count,'joined_row_count',joined_row_count,
  'run_metadata_valid',run_metadata_valid,
  'projection_metadata_bound',projection_metadata_bound,
  'stored_report_manifest_present',stored_report_manifest_present,
  'storage_metadata_shape_valid',storage_metadata_shape_valid,
  'compressed_envelope_present',compressed_envelope_present,
  'observation_sha256', CASE WHEN ledger_valid AND run_count=1 AND joined_row_count=1 AND run_metadata_valid
                    AND projection_metadata_bound AND stored_report_manifest_present
                    AND storage_metadata_shape_valid THEN observation_sha256 ELSE NULL END,
  'canonical_payload_deserialized',false,'canonical_integrity_recomputed',false,
  'projection_hash_recomputed',false,'report_bytes_verified',false,
  'restore_provenance_verified',false,'evidence_record_written',false
) FROM summary CROSS JOIN ledger_check;
\else
SELECT jsonb_build_object('status','blocked',
 'scope','exact_run_canonical_row_and_stored_browser_manifest_metadata_v2',
 'contract_missing_columns', :contract_missing_columns,
 'comprehensive_missing_columns', :comprehensive_missing_columns,
 'required_contract_columns_verified', :contract_missing_columns = 0,
 'comprehensive_columns_verified', :comprehensive_missing_columns = 0,
 'observation_sha256',NULL, 'canonical_payload_deserialized',false,
 'canonical_integrity_recomputed',false,'projection_hash_recomputed',false,
 'report_bytes_verified',false,'restore_provenance_verified',false,'evidence_record_written',false);
\endif
ROLLBACK;
READ_ONLY_SQL
then printf 'observation_transaction_closed\n'; else printf 'observation_failed\n'; exit 1; fi
