SELECT CAST(opened_date AS STRING) opened_date,COUNT(*) requests
        FROM workspace.service_request_analytics_full.cleaned_requests WHERE batch_id=:batch GROUP BY opened_date
