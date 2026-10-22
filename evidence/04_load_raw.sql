MERGE INTO workspace.service_request_analytics_full.raw_requests t USING (SELECT * FROM read_files('/Volumes/workspace/service_request_analytics_full/landing/20261021T141250867855Z/records.ndjson',format=>'json',schema=>'batch_id STRING,request_id STRING,payload_json STRING,payload_sha256 STRING,fetched_at STRING,source_endpoint STRING,cohort_start STRING,cohort_end STRING')) s
      ON t.batch_id=s.batch_id AND t.request_id=s.request_id
      WHEN NOT MATCHED THEN INSERT (batch_id,request_id,payload_json,payload_sha256,fetched_at,source_endpoint,cohort_start,cohort_end,loaded_at)
      VALUES(s.batch_id,s.request_id,s.payload_json,s.payload_sha256,s.fetched_at,s.source_endpoint,s.cohort_start,s.cohort_end,current_timestamp())
