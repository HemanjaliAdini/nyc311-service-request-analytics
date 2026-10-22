SELECT request_id,coalesce(category,'Unknown'),coalesce(agency,'Unknown'),
      coalesce(status,'Unknown'),coalesce(borough,'Unknown'),coalesce(channel,'Unknown'),
      CAST(opened_at AS STRING),CAST(closed_at AS STRING),CAST(opened_date AS STRING),
      hours_to_close,duration_quality,not_closed,open_age_calendar_days,1 request_count,
      CASE WHEN open_age_calendar_days IS NULL THEN 'Not applicable'
           WHEN open_age_calendar_days<7 THEN '01. Under 7 days'
           WHEN open_age_calendar_days<30 THEN '02. 7-29 days'
           WHEN open_age_calendar_days<60 THEN '03. 30-59 days'
           ELSE '04. 60+ days' END open_age_band
      FROM workspace.service_request_analytics_full.cleaned_requests WHERE batch_id=:batch ORDER BY request_id
