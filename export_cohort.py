"""Refresh the Tableau CSV from a verified Databricks cohort, without reloading it."""
import argparse
import hashlib
import json
from pathlib import Path
import run_cohort_cloud as cloud


def export(run):
    validation=json.loads((run/'validation.json').read_text())
    rows=cloud.sql(run,'20_tableau_export',f'''SELECT request_id,coalesce(category,'Unknown'),coalesce(agency,'Unknown'),
      coalesce(status,'Unknown'),coalesce(borough,'Unknown'),coalesce(channel,'Unknown'),
      CAST(opened_at AS STRING),CAST(closed_at AS STRING),CAST(opened_date AS STRING),
      hours_to_close,duration_quality,not_closed,open_age_calendar_days,1 request_count,
      CASE WHEN open_age_calendar_days IS NULL THEN 'Not applicable'
           WHEN open_age_calendar_days<7 THEN '01. Under 7 days'
           WHEN open_age_calendar_days<30 THEN '02. 7-29 days'
           WHEN open_age_calendar_days<60 THEN '03. 30-59 days'
           ELSE '04. 60+ days' END open_age_band
      FROM {cloud.SCHEMA}.cleaned_requests WHERE batch_id=:batch ORDER BY request_id''',
      [{'name':'batch','value':run.name}])
    assert len(rows)==validation['row_count']
    assert sum(int(r[13]) for r in rows)==validation['row_count']
    assert sum(int(r[11] or 0) for r in rows)==int(validation['summary'][4])
    path=cloud.BASE/'tableau'/'cohort'/'requests.csv'
    cloud.write_csv(path,['request_id','category','agency','status','borough','channel','opened_at','closed_at','opened_date','hours_to_close','duration_quality','not_closed','open_age_calendar_days','request_count','open_age_band'],rows)
    validation['export_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (run/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    m=json.loads((path.parent/'manifest.json').read_text());m['validation']=validation
    (path.parent/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    print('Tableau request-level export verified:',len(rows),'rows',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path)
    export(p.parse_args().run.resolve())
