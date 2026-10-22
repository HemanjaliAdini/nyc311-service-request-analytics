"""Load a complete extracted cohort, verify replay, and export Databricks reports."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
from zoneinfo import ZoneInfo

import load_raw_databricks as db

BASE = Path(__file__).resolve().parent
SCHEMA = 'workspace.service_request_analytics_full'
LANDING = '/Volumes/workspace/service_request_analytics_full/landing'


def sql(run, label, statement, parameters=None):
    evidence=run/'cloud'
    evidence.mkdir(exist_ok=True)
    (evidence/f'{label}.sql').write_text(statement+'\n')
    response=db.api('post','/api/2.0/sql/statements',{
        'warehouse_id':db.WAREHOUSE,'statement':statement,'parameters':parameters or [],
        'wait_timeout':'10s','on_wait_timeout':'CONTINUE','disposition':'INLINE'})
    deadline=time.monotonic()+300
    while response['status']['state'] in ('PENDING','RUNNING'):
        (evidence/f'{label}.json').write_text(json.dumps(response,indent=2))
        if time.monotonic()>deadline:
            raise RuntimeError('SQL still active: inspect saved statement ID before resuming')
        time.sleep(3)
        response=db.api('get','/api/2.0/sql/statements/'+response['statement_id'])
    (evidence/f'{label}.json').write_text(json.dumps(response,indent=2)+'\n')
    if response['status']['state']!='SUCCEEDED':
        raise RuntimeError(str(response['status']))
    result=response.get('result',{})
    rows=list(result.get('data_array',[]))
    link=result.get('next_chunk_internal_link')
    while link:
        chunk=db.api('get',link)
        rows.extend(chunk.get('data_array',[]))
        link=chunk.get('next_chunk_internal_link')
    if response.get('manifest',{}).get('truncated'):
        raise ValueError('SQL results truncated')
    if rows and len(rows)!=response['manifest']['total_row_count']:
        raise ValueError('SQL result chunks incomplete')
    print(label+': SUCCEEDED',flush=True)
    return rows


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cloud_fingerprint(run,label,table,params):
    return sql(run,label,f'''SELECT COUNT(*),COUNT(DISTINCT request_id),
      sha2(concat_ws('',sort_array(collect_list(concat(request_id,':',payload_sha256)))),256),
      sha2(to_json(sort_array(collect_list(to_json(struct(*))))),256)
      FROM {SCHEMA}.{table} WHERE batch_id=:batch''',params)


def write_csv(path,columns,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(columns);w.writerows(rows)


def run_cloud(run):
    run=run.resolve()
    manifest=json.loads((run/'manifest.json').read_text())
    if manifest['status']!='extracted_and_count_reconciled' or file_sha(run/'records.ndjson')!=manifest['records_sha256']:
        raise ValueError('Extraction manifest/hash invalid')
    records=[json.loads(line) for line in (run/'records.ndjson').read_text().splitlines()]
    assert len(records)==len({r['request_id'] for r in records})==manifest['row_count']
    for page in manifest['pages']:
        assert file_sha(run/page['file'])==page['sha256']
    snapshot_local=datetime.fromisoformat(manifest['finished_at_utc']).astimezone(ZoneInfo('America/New_York')).replace(tzinfo=None)
    params=[{'name':'batch','value':run.name},{'name':'snapshot_local','value':snapshot_local.isoformat()}]
    sql(run,'01_schema',f"CREATE SCHEMA IF NOT EXISTS {SCHEMA} COMMENT 'NYC 311 complete creation cohort; separate from five-row lessons'")
    sql(run,'02_volume',f'CREATE VOLUME IF NOT EXISTS {SCHEMA}.landing')
    path=f'{LANDING}/{run.name}'
    for cmd in [ ['fs','mkdir','dbfs:'+path], ['fs','cp',str(run/'records.ndjson'),'dbfs:'+path+'/records.ndjson'] ]:
        completed=subprocess.run([db.CLI,*cmd,'--profile',db.PROFILE],env=db.ENV,capture_output=True,text=True,timeout=180)
        if completed.returncode and not ('already exists' in completed.stderr.lower()):
            raise RuntimeError(completed.stderr)
    raw_source=f"SELECT * FROM read_files('{path}/records.ndjson',format=>'json',schema=>'batch_id STRING,request_id STRING,payload_json STRING,payload_sha256 STRING,fetched_at STRING,source_endpoint STRING,cohort_start STRING,cohort_end STRING')"
    sql(run,'03_raw_table',f'''CREATE TABLE IF NOT EXISTS {SCHEMA}.raw_requests (
      batch_id STRING,request_id STRING,payload_json STRING,payload_sha256 STRING,
      fetched_at STRING,source_endpoint STRING,cohort_start STRING,cohort_end STRING,
      loaded_at TIMESTAMP) USING DELTA''')
    raw_merge=f'''MERGE INTO {SCHEMA}.raw_requests t USING ({raw_source}) s
      ON t.batch_id=s.batch_id AND t.request_id=s.request_id
      WHEN NOT MATCHED THEN INSERT (batch_id,request_id,payload_json,payload_sha256,fetched_at,source_endpoint,cohort_start,cohort_end,loaded_at)
      VALUES(s.batch_id,s.request_id,s.payload_json,s.payload_sha256,s.fetched_at,s.source_endpoint,s.cohort_start,s.cohort_end,current_timestamp())'''
    sql(run,'04_load_raw',raw_merge)
    raw_before=cloud_fingerprint(run,'05_verify_raw','raw_requests',params[:1])
    expected_hash=hashlib.sha256(''.join(sorted(r['request_id']+':'+r['payload_sha256'] for r in records)).encode()).hexdigest()
    assert [int(x) for x in raw_before[0][:2]]==[len(records)]*2
    assert raw_before[0][2]==expected_hash
    # Prove stored JSON agrees with its checksum, not just with a copied hash column.
    bad=sql(run,'06_payload_integrity',f'''SELECT COUNT(*) FROM {SCHEMA}.raw_requests
      WHERE batch_id=:batch AND sha2(payload_json,256)<>payload_sha256''',params[:1])
    assert int(bad[0][0])==0
    clean=(BASE/'cohort_clean.sql').read_text()
    sql(run,'07_clean_table',f'CREATE TABLE IF NOT EXISTS {SCHEMA}.cleaned_requests USING DELTA AS SELECT *,current_timestamp() cleaned_at FROM ({clean}) WHERE 1=0',params)
    clean_merge=f'''MERGE INTO {SCHEMA}.cleaned_requests t USING ({clean}) s
      ON t.batch_id=s.batch_id AND t.request_id=s.request_id
      WHEN NOT MATCHED THEN INSERT * EXCEPT (cleaned_at)'''
    # Explicit column mapping preserves the original cleaning timestamp on replay.
    columns=['batch_id','request_id','category','agency','status','borough','channel','opened_at','closed_at','opened_date','hours_to_close','duration_quality','not_closed','open_age_calendar_days','fetched_at','source_endpoint','cohort_start','cohort_end','payload_sha256','transformation_version']
    clean_merge=f'''MERGE INTO {SCHEMA}.cleaned_requests t USING ({clean}) s
      ON t.batch_id=s.batch_id AND t.request_id=s.request_id
      WHEN NOT MATCHED THEN INSERT ({','.join(columns)},cleaned_at)
      VALUES ({','.join('s.'+c for c in columns)},current_timestamp())'''
    sql(run,'08_load_clean',clean_merge,params)
    before=cloud_fingerprint(run,'09_clean_fingerprint','cleaned_requests',params[:1])
    assert [int(x) for x in before[0][:2]]==[len(records)]*2
    assert before[0][2]==expected_hash
    export=sql(run,'10_export_cleaned',f'''SELECT request_id,coalesce(category,'Unknown'),coalesce(agency,'Unknown'),coalesce(status,'Unknown'),
      coalesce(borough,'Unknown'),coalesce(channel,'Unknown'),CAST(opened_at AS STRING),CAST(closed_at AS STRING),
      CAST(opened_date AS STRING),hours_to_close,duration_quality,not_closed,open_age_calendar_days,
      1 request_count,
      CASE WHEN open_age_calendar_days IS NULL THEN 'Not applicable'
           WHEN open_age_calendar_days<7 THEN '01. Under 7 days'
           WHEN open_age_calendar_days<30 THEN '02. 7-29 days'
           WHEN open_age_calendar_days<60 THEN '03. 30-59 days'
           ELSE '04. 60+ days' END open_age_band
      FROM {SCHEMA}.cleaned_requests WHERE batch_id=:batch ORDER BY request_id''',params[:1])
    originals={r['request_id']:json.loads(r['payload_json']) for r in records}
    assert len(export)==len(originals)
    for row in export:
        p=originals[row[0]]
        assert row[1:6]==[(p.get(k) or '').strip() or 'Unknown' for k in ['complaint_type','agency','status','borough','open_data_channel_type']]
        assert datetime.fromisoformat(row[6])==datetime.fromisoformat(p['created_date'])
        if row[10]=='valid':
            expected=(datetime.fromisoformat(p['closed_date'])-datetime.fromisoformat(p['created_date'])).total_seconds()/3600
            assert abs(float(row[9])-expected)<0.000001 and p['status'].lower()=='closed'
        else:
            assert row[9] is None
    sql(run,'11_replay_raw',raw_merge)
    sql(run,'12_replay_clean',clean_merge,params)
    assert raw_before==cloud_fingerprint(run,'13_verify_raw_replay','raw_requests',params[:1])
    assert before==cloud_fingerprint(run,'14_verify_clean_replay','cleaned_requests',params[:1])
    queries={
      'category':f'''SELECT coalesce(category,'Unknown') category,COUNT(*) requests,COUNT(hours_to_close) valid_closed,
        AVG(hours_to_close) average_hours,PERCENTILE(hours_to_close,0.5) median_hours,
        SUM(CASE WHEN not_closed=1 THEN 1 ELSE 0 END) not_closed,
        SUM(CASE WHEN not_closed IS NULL THEN 1 ELSE 0 END) unknown_status
        FROM {SCHEMA}.cleaned_requests WHERE batch_id=:batch GROUP BY category''',
      'daily':f'''SELECT CAST(opened_date AS STRING) opened_date,COUNT(*) requests
        FROM {SCHEMA}.cleaned_requests WHERE batch_id=:batch GROUP BY opened_date''',
      'summary':f'''SELECT COUNT(*) requests,COUNT(hours_to_close) valid_closed,AVG(hours_to_close) average_hours,
        PERCENTILE(hours_to_close,0.5) median_hours,
        SUM(CASE WHEN not_closed=1 THEN 1 ELSE 0 END) not_closed,
        SUM(CASE WHEN not_closed IS NULL THEN 1 ELSE 0 END) unknown_status
        FROM {SCHEMA}.cleaned_requests WHERE batch_id=:batch''',
    }
    reports={}
    for name,query in queries.items():
        sql(run,'15_view_'+name,f'CREATE OR REPLACE VIEW {SCHEMA}.report_{name}_{run.name.lower()} AS '+query.replace(':batch',"'"+run.name+"'"))
        reports[name]=sql(run,'16_report_'+name,query,params[:1])
    assert sum(int(r[1]) for r in reports['category'])==len(records)
    assert sum(int(r[1]) for r in reports['daily'])==len(records)
    expected_categories=Counter((p.get('complaint_type','').strip() or 'Unknown') for p in originals.values())
    assert {r[0]:int(r[1]) for r in reports['category']}==expected_categories
    valid_hours=[float(r[9]) for r in export if r[9] is not None]
    assert int(reports['summary'][0][1])==len(valid_hours)
    assert abs(float(reports['summary'][0][3])-statistics.median(valid_hours))<0.000001
    # Export from Databricks, one row per request, so Tableau filters recompute averages correctly.
    out=BASE/'tableau'/'cohort'
    out.mkdir(exist_ok=True)
    headers=['request_id','category','agency','status','borough','channel','opened_at','closed_at','opened_date','hours_to_close','duration_quality','not_closed','open_age_calendar_days','request_count','open_age_band']
    write_csv(run/'cloud'/'requests.csv',headers,export)
    write_csv(out/'requests.csv',headers,export)
    for name,rows in reports.items():
        (run/'cloud'/f'report_{name}.json').write_text(json.dumps(rows,indent=2)+'\n')
    validation={'batch_id':run.name,'row_count':len(records),'raw_hash_match':True,'stored_payload_hashes_match':True,
       'cleaned_source_fields_and_durations_match':True,'replay_raw_and_cleaned_full_contents_unchanged':True,
       'report_totals_and_category_counts_match':True,'median_matches_independent_calculation':True,
       'summary':reports['summary'][0],'quality_counts':dict(Counter(r[10] for r in export)),
       'scope':manifest['scope'],'snapshot_local_assumption':'America/New_York for future-date checks and calendar-day ageing; source times have no explicit offset',
       'duration_semantics':'Source wall-clock hours, not UTC elapsed time; reject future, reversed and invalid closure dates',
       'export_sha256':file_sha(out/'requests.csv'),'schedule':'manual; no schedule created'}
    (run/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({**manifest,'validation':validation},indent=2)+'\n')
    (BASE/'LATEST_COHORT.json').write_text(json.dumps({'run_directory':str(run),'batch_id':run.name,'status':'cloud_verified','export':str(out/'requests.csv')},indent=2)+'\n')
    print('VERIFIED COHORT:',len(export),'requests',json.dumps(validation['quality_counts']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    run_cloud(parser.parse_args().run)
