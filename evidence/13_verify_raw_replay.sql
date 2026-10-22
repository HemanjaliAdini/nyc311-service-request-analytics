SELECT COUNT(*),COUNT(DISTINCT request_id),
      sha2(concat_ws('',sort_array(collect_list(concat(request_id,':',payload_sha256)))),256),
      sha2(to_json(sort_array(collect_list(to_json(struct(*))))),256)
      FROM workspace.service_request_analytics_full.raw_requests WHERE batch_id=:batch
