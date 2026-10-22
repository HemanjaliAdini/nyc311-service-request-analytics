# Manual refresh and operation

## Prerequisites

Python 3.9+, Tableau Public, the official Databricks CLI authenticated to your own workspace, an existing SQL warehouse and permission to create/use the project schema and managed volume. Scripts use `workspace.service_request_analytics_full`; inspect it before running in an existing workspace. No credentials are included.

Set your configuration locally:

```sh
export DATABRICKS_PROFILE=YOUR_PROFILE
export DATABRICKS_WAREHOUSE_ID=YOUR_WAREHOUSE_ID
# Optional when your CLI or config is outside the normal search path:
# export DATABRICKS_CLI=/absolute/path/to/databricks
# export DATABRICKS_CONFIG_FILE=/absolute/path/to/config
```

Do not commit your local config, tokens or environment file. The CLI uses your existing authentication; no token is stored in Python code.

## Fresh run

```sh
python3 extract_cohort.py --start 2026-09-01 --end 2026-09-08
```

Use the NEW directory printed after `COMPLETE:` below, replacing `NEW_BATCH`. Execute commands sequentially, stopping on any error:

```sh
python3 run_cohort_cloud.py cohorts/NEW_BATCH
python3 export_cohort.py cohorts/NEW_BATCH
```

For extract generation, use an isolated environment with Tableau's official API:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-tableau.txt
python build_hyper_extract.py
python build_tableau_dashboard.py
python verify_tableau_package.py
```

Tableau's local engine needs permission to create a local socket. Rebuilds replace the current files in `tableau/cohort`; copy previous artifacts first if you want to retain a separate workbook for each run. Original API pages/cloud evidence remain under their batch directories. No recurring job is installed.

The delivered workbook is native-verified. The portable configuration copy is locally checked but has not been run against a second user's cloud workspace. The workbook title currently identifies the delivered September window; update the title generation before using a different date window.

## Failure recovery

Do not run concurrent writers. On a SQL timeout, inspect the saved statement ID/server state before retrying: the statement may still be running. Do not delete tables to recover. An existing landing file must match the intended batch; a partial upload requires investigation. Raw/cleaned insert-only MERGE replay was checked for the delivered batch, including timestamps. If only export failed, resume `export_cohort.py` for that verified batch.

## Acceptance

Open the `.twbx` in Tableau Public. Check all six charts and the three filters, resetting each to All. Dashboard baseline totals remain static; chart data is filtered. Keep the snapshot date and source wall-clock duration caveat visible. Local save and public Tableau publication are separate actions; the dashboard has not been published to Tableau Public.
