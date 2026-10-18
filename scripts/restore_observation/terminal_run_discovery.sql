-- REVIEW CANDIDATE ONLY. No live execution performed.
-- Discover at most three existing terminal Comprehensive run identities.
-- Only non-secret run IDs, revisions and commit hashes may be returned.
-- No payload, repository, customer/project, report text or credentials selected.
-- Same previously reviewed clean-env/auth-none local-socket wrapper required.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = 3000;
SET LOCAL lock_timeout = 1000;
SET LOCAL idle_in_transaction_session_timeout = 10000;
SET LOCAL search_path = pg_catalog;
WITH sampled AS MATERIALIZED (
  SELECT left(run_id,129) AS run_id, revision, left(commit_sha,41) AS commit_sha
  FROM public.nico_comprehensive_runs
  WHERE terminal IS TRUE
  ORDER BY run_id
  LIMIT 3
), checked AS (
  SELECT *, coalesce(run_id ~ '^[A-Za-z0-9_-]{1,128}$'
                     AND length(run_id) <= 128
                     AND commit_sha ~ '^[0-9a-f]{40}$'
                     AND length(commit_sha) = 40
                     AND revision >= 0, false) AS valid
  FROM sampled
)
SELECT jsonb_build_object(
  'scope','existing_terminal_comprehensive_run_metadata_discovery_v1',
  'discovery_only',true,
  'transaction_read_only',current_setting('transaction_read_only')='on',
  'repeatable_read',current_setting('transaction_isolation')='repeatable read',
  'sample_count',count(*),
  'metadata_valid',coalesce(bool_and(valid),false),
  'runs',coalesce(jsonb_agg(jsonb_build_object(
     'run_id',CASE WHEN valid THEN run_id ELSE NULL END,
     'revision',CASE WHEN valid THEN revision ELSE NULL END,
     'commit_sha',CASE WHEN valid THEN commit_sha ELSE NULL END
  ) ORDER BY run_id),'[]'::jsonb),
  'historical_report_identity_independently_matched',false,
  'canonical_payload_deserialized',false,
  'report_bytes_verified',false,'restore_provenance_verified',false,
  'evidence_record_written',false
) FROM checked;
ROLLBACK;
