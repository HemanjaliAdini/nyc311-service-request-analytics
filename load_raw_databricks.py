"""Databricks CLI transport using the caller's existing authenticated profile."""
import json
import os
import shutil
import subprocess

CLI = os.environ.get('DATABRICKS_CLI') or shutil.which('databricks') or 'databricks'
ENV = dict(os.environ)
PROFILE = os.environ.get('DATABRICKS_PROFILE', 'DEFAULT')
WAREHOUSE = os.environ.get('DATABRICKS_WAREHOUSE_ID', '')

def api(method, path, payload=None):
    if not WAREHOUSE:
        raise ValueError('Set DATABRICKS_WAREHOUSE_ID to your SQL warehouse ID')
    command = [CLI, 'api', method, path, '--profile', PROFILE, '--output', 'json']
    if payload is not None:
        command += ['--json', json.dumps(payload)]
    result = subprocess.run(command, env=ENV, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)
