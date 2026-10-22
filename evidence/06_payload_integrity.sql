SELECT COUNT(*) FROM workspace.service_request_analytics_full.raw_requests
      WHERE batch_id=:batch AND sha2(payload_json,256)<>payload_sha256
