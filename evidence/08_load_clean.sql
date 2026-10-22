MERGE INTO workspace.service_request_analytics_full.cleaned_requests t USING (WITH parsed AS (
 SELECT *, from_json(payload_json,
 'unique_key STRING, created_date STRING, closed_date STRING, complaint_type STRING, status STRING, agency STRING, borough STRING, open_data_channel_type STRING') p
 FROM workspace.service_request_analytics_full.raw_requests WHERE batch_id=:batch
), typed AS (
 SELECT *,
  try_cast(p.created_date AS TIMESTAMP_NTZ) opened_at,
  try_cast(p.closed_date AS TIMESTAMP_NTZ) closed_at,
  nullif(trim(p.complaint_type),'') category,
  nullif(trim(p.agency),'') agency,
  nullif(trim(p.status),'') status,
  nullif(trim(p.borough),'') borough,
  nullif(trim(p.open_data_channel_type),'') channel,
  try_cast(:snapshot_local AS TIMESTAMP_NTZ) snapshot_local
 FROM parsed
), checked AS (
 SELECT *, CASE
  WHEN p.unique_key IS NULL OR p.unique_key<>request_id THEN 'invalid_payload_id'
  WHEN opened_at IS NULL THEN 'invalid_opened_at'
  WHEN opened_at>snapshot_local THEN 'future_opened_at'
  WHEN nullif(trim(p.closed_date),'') IS NULL THEN 'missing_closed_date'
  WHEN closed_at IS NULL THEN 'invalid_closed_at'
  WHEN closed_at<opened_at THEN 'negative_duration'
  WHEN closed_at>snapshot_local THEN 'future_closed_at'
  WHEN coalesce(lower(status),'')<>'closed' THEN 'closure_status_mismatch'
  ELSE 'valid' END duration_quality
 FROM typed
)
SELECT batch_id,request_id,category,agency,status,borough,channel,opened_at,closed_at,
 CAST(opened_at AS DATE) opened_date,
 CASE WHEN duration_quality='valid' THEN timestampdiff(SECOND,opened_at,closed_at)/3600.0 END hours_to_close,
 duration_quality,
 CASE WHEN status IS NULL OR lower(status)='unspecified' THEN NULL
      WHEN lower(status)='closed' THEN 0 ELSE 1 END not_closed,
 CASE WHEN status IS NOT NULL AND lower(status) NOT IN ('closed','unspecified')
       AND opened_at IS NOT NULL AND opened_at<=snapshot_local
      THEN datediff(CAST(snapshot_local AS DATE),CAST(opened_at AS DATE)) END open_age_calendar_days,
 fetched_at,source_endpoint,cohort_start,cohort_end,payload_sha256,
 'v2' transformation_version
FROM checked
) s
      ON t.batch_id=s.batch_id AND t.request_id=s.request_id
      WHEN NOT MATCHED THEN INSERT (batch_id,request_id,category,agency,status,borough,channel,opened_at,closed_at,opened_date,hours_to_close,duration_quality,not_closed,open_age_calendar_days,fetched_at,source_endpoint,cohort_start,cohort_end,payload_sha256,transformation_version,cleaned_at)
      VALUES (s.batch_id,s.request_id,s.category,s.agency,s.status,s.borough,s.channel,s.opened_at,s.closed_at,s.opened_date,s.hours_to_close,s.duration_quality,s.not_closed,s.open_age_calendar_days,s.fetched_at,s.source_endpoint,s.cohort_start,s.cohort_end,s.payload_sha256,s.transformation_version,current_timestamp())
