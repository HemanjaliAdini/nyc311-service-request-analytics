"""Extract a complete creation-date cohort through the public NYC 311 API."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
ENDPOINT = 'https://data.cityofnewyork.us/resource/erm2-nwe9.json'
FIELDS = 'unique_key,created_date,closed_date,complaint_type,status,agency,borough,open_data_channel_type'


def get_json(parameters, attempts=4, opener=urlopen, sleeper=time.sleep):
    url = ENDPOINT + '?' + urlencode(parameters)
    for attempt in range(attempts):
        try:
            with opener(Request(url, headers={'Accept': 'application/json'}), timeout=90) as response:
                raw = response.read()
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError('Expected an API list')
            return data, raw, url
        except (HTTPError, URLError, TimeoutError) as error:
            if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == attempts - 1:
                raise
            # Bounded backoff; honour a numeric Retry-After up to 30 seconds.
            retry = error.headers.get('Retry-After') if isinstance(error, HTTPError) else None
            delay = min(30, float(retry)) if retry and retry.isdigit() else 2 ** attempt
            sleeper(delay)
    raise RuntimeError('No response')


def extract(start, end, page_size=3000):
    date.fromisoformat(start)
    date.fromisoformat(end)
    if start >= end or not 1 <= page_size <= 10000:
        raise ValueError('Use increasing dates and a page size from 1 to 10000')
    started = datetime.now(timezone.utc)
    run = BASE / 'cohorts' / started.strftime('%Y%m%dT%H%M%S%fZ')
    (run / 'pages').mkdir(parents=True, exist_ok=False)
    predicate = f"created_date >= '{start}T00:00:00' AND created_date < '{end}T00:00:00'"
    count_before = int(get_json({'$select':'count(*) AS n', '$where':predicate})[0][0]['n'])
    seen, rows, pages, cursor = set(), [], [], None
    while True:
        where = predicate
        if cursor:
            created, key = cursor
            if not key.isdigit():
                raise ValueError('Unexpected nonnumeric ID in cursor')
            datetime.fromisoformat(created)
            where += f" AND (created_date > '{created}' OR (created_date = '{created}' AND unique_key > '{key}'))"
        data, raw, url = get_json({'$select':FIELDS, '$where':where,
                                  '$order':'created_date ASC,unique_key ASC', '$limit':page_size})
        page = len(pages) + 1
        filename = f'pages/page-{page:04d}.json'
        (run / filename).write_bytes(raw)
        pages.append({'file':filename, 'rows':len(data), 'url':url,
                      'sha256':hashlib.sha256(raw).hexdigest()})
        for record in data:
            key = record.get('unique_key')
            opened = record.get('created_date')
            if not key or not opened or key in seen:
                raise ValueError('Missing ID/date or duplicate request across pages')
            if not start <= opened[:10] < end:
                raise ValueError('Record outside cohort window')
            position = (opened, key)
            if cursor and position <= cursor:
                raise ValueError('API pagination did not advance')
            cursor = position
            seen.add(key)
            rows.append(record)
        print(f'Page {page}: {len(data)} records; total {len(rows)}', flush=True)
        if len(data) < page_size:
            break
    count_after = int(get_json({'$select':'count(*) AS n', '$where':predicate})[0][0]['n'])
    if len(rows) != count_before or count_after != count_before:
        raise ValueError('Cohort count changed or extraction is incomplete; do not load this run')
    ended = datetime.now(timezone.utc)
    manifest = {
        'batch_id':run.name, 'start_inclusive':start, 'end_exclusive':end,
        'started_at_utc':started.isoformat(), 'finished_at_utc':ended.isoformat(),
        'row_count':len(rows), 'api_count_before':count_before, 'api_count_after':count_after,
        'page_size':page_size, 'pages':pages, 'endpoint':ENDPOINT,
        'scope': 'All available API records created in the window; API is mutable, pages are not a transactionally consistent snapshot',
        'status':'extracted_and_count_reconciled',
    }
    records_path = run / 'records.ndjson'
    with records_path.open('w', encoding='utf-8') as output:
        for record in rows:
            payload = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            output.write(json.dumps({'batch_id':run.name, 'request_id':record['unique_key'],
                'payload_json':payload, 'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),
                'fetched_at':ended.isoformat(), 'source_endpoint':ENDPOINT,
                'cohort_start':start, 'cohort_end':end}, ensure_ascii=False) + '\n')
    manifest['records_sha256'] = hashlib.sha256(records_path.read_bytes()).hexdigest()
    (run / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('COMPLETE:', run, flush=True)
    return run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2026-09-01')
    parser.add_argument('--end', default='2026-09-08')
    parser.add_argument('--page-size', type=int, default=3000)
    args = parser.parse_args()
    extract(args.start, args.end, args.page_size)
