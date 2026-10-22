CREATE OR REPLACE VIEW workspace.service_request_analytics_full.report_daily_20261021t141250867855z AS SELECT CAST(opened_date AS STRING) opened_date,COUNT(*) requests
        FROM workspace.service_request_analytics_full.cleaned_requests WHERE batch_id='20261021T141250867855Z' GROUP BY opened_date
