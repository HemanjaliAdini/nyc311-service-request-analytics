"""File consistency checks, separate from native Tableau acceptance."""
import csv
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile
BASE=Path(__file__).resolve().parent

def verify():
    folder=BASE/'tableau'/'cohort'
    metadata=json.loads((folder/'manifest.json').read_text())
    expected=metadata['validation']
    with zipfile.ZipFile(folder/'NYC 311 Service Request Analytics.twbx') as package:
        assert package.testzip() is None
        names=package.namelist()
        root=E.fromstring(package.read(next(n for n in names if n.endswith('.twb'))))
        raw=package.read(next(n for n in names if n.endswith('requests.csv')))
        assert hashlib.sha256(raw).hexdigest()==expected['export_sha256']
        assert raw==(folder/'requests.csv').read_bytes()
        records=list(csv.DictReader(io.StringIO(raw.decode())))
        assert len(records)==expected['row_count']
        assert sum(int(r['request_count']) for r in records)==expected['row_count']
        assert sum(int(r['not_closed'] or 0) for r in records)==int(expected['summary'][4])
        sheets={s.get('name') for s in root.findall('./worksheets/worksheet')}
        assert len(sheets)==6
        extract=root.find('./datasources/datasource/extract/connection')
        assert extract is not None and extract.get('dbname')=='Data/requests.hyper'
        hyper=json.loads((folder/'hyper_validation.json').read_text())
        assert hashlib.sha256(package.read('Data/requests.hyper')).hexdigest()==hyper['hyper_sha256']
        assert hyper['all_typed_fields_match_csv'] and hyper['row_count']==expected['row_count']
        filters=root.findall("./dashboards/dashboard/zones//zone[@type-v2='filter']")
        assert len(filters)==3
        result={'batch_id':metadata['batch_id'],'rows':len(records),'sheets':sorted(sheets),'filter_controls':len(filters),'csv_hash_matches':True}
        (folder/'package_validation.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))

if __name__=='__main__': verify()
