CREATE OR REPLACE VIEW workspace.service_request_analytics_full.report_summary_20261021t141250867855z AS SELECT COUNT(*) requests,COUNT(hours_to_close) valid_closed,AVG(hours_to_close) average_hours,
        PERCENTILE(hours_to_close,0.5) median_hours,
        SUM(CASE WHEN not_closed=1 THEN 1 ELSE 0 END) not_closed,
        SUM(CASE WHEN not_closed IS NULL THEN 1 ELSE 0 END) unknown_status
        FROM workspace.service_request_analytics_full.cleaned_requests WHERE batch_id='20261021T141250867855Z'
