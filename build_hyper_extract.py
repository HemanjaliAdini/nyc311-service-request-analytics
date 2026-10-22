"""Create and independently reconcile the Tableau Public extract.

Requires Tableau's official tableauhyperapi Python package and cffi.
"""
import csv
import hashlib
import json
from pathlib import Path
from tableauhyperapi import HyperProcess, Connection, Telemetry, CreateMode, TableDefinition, TableName, SqlType, Inserter

BASE=Path(__file__).resolve().parent/'tableau'/'cohort'

def main():
    source=BASE/'requests.csv'
    with source.open(newline='') as f:
        reader=csv.DictReader(f); names=reader.fieldnames; records=list(reader)
    integer={'not_closed','open_age_calendar_days','request_count'}
    real={'hours_to_close'}
    definition=TableDefinition(TableName('Extract','Extract'),[
        TableDefinition.Column(n,SqlType.big_int() if n in integer else SqlType.double() if n in real else SqlType.text()) for n in names])
    rows=[[None if r[n]=='' else int(r[n]) if n in integer else float(r[n]) if n in real else r[n] for n in names] for r in records]
    target=BASE/'requests.hyper'
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,parameters={'log_dir':str(BASE)}) as process:
        with Connection(process.endpoint,str(target),CreateMode.CREATE_AND_REPLACE) as connection:
            connection.catalog.create_schema('Extract');connection.catalog.create_table(definition)
            with Inserter(connection,definition) as inserter:
                inserter.add_rows(rows);inserter.execute()
            actual=connection.execute_list_query('SELECT * FROM "Extract"."Extract"')
            # Exact comparison of every typed field, independent of storage order.
            assert sorted(actual,key=lambda r:r[0])==sorted(rows,key=lambda r:r[0])
    result={'row_count':len(rows),'all_typed_fields_match_csv':True,'csv_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'hyper_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (BASE/'hyper_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
