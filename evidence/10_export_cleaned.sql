SELECT request_id,coalesce(category,'Unknown'),coalesce(agency,'Unknown'),coalesce(status,'Unknown'),
      coalesce(borough,'Unknown'),coalesce(channel,'Unknown'),CAST(opened_at AS STRING),CAST(closed_at AS STRING),
      CAST(opened_date AS STRING),hours_to_close,duration_quality,not_closed,open_age_calendar_days
      FROM workspace.service_request_analytics_full.cleaned_requests WHERE batch_id=:batch ORDER BY request_id
