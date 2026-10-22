CREATE TABLE IF NOT EXISTS workspace.service_request_analytics_full.raw_requests (
      batch_id STRING,request_id STRING,payload_json STRING,payload_sha256 STRING,
      fetched_at STRING,source_endpoint STRING,cohort_start STRING,cohort_end STRING,
      loaded_at TIMESTAMP) USING DELTA
