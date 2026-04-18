import json
import subprocess
import sys
import uuid

import pandas as pd
from prefect import flow, task

sys.path.insert(0, '.')
from src.ingestion import validate_dataframe, fetch_from_api, merge_sources
from src.transform import run_model
from src.logger import get_logger
from src.monitor import collect_metrics, save_metrics, detect_drift

RUN_ID = str(uuid.uuid4())[:8]
log = get_logger("pipeline")

METRICS_PATH = 'data/monitoring/metrics_history.jsonl'


@task(name="Ingest CSV")
def ingest_csv():
    df = pd.read_csv('data/raw/cs-training.csv', index_col=0)
    log.info("CSV ingerido", extra={"run_id": RUN_ID, "records": len(df)})
    return df


@task(name="Validate")
def validate(df):
    report = validate_dataframe(df)
    level = log.warning if not report['is_valid'] else log.info
    level("Qualidade validada", extra={"run_id": RUN_ID, **report})
    return report


@task(name="Fetch API")
def fetch_api():
    data = fetch_from_api(5000)
    with open('data/raw/bureau_api.json', 'w') as f:
        json.dump(data, f)
    log.info("API simulada consultada", extra={"run_id": RUN_ID, "records": len(data)})


@task(name="Merge")
def merge():
    df = merge_sources('data/raw/cs-training.csv', 'data/raw/bureau_api.json')
    log.info("Fontes mescladas", extra={"run_id": RUN_ID, "records": len(df)})
    return df


@task(name="Run Staging")
def run_staging():
    run_model('stg_credit_applications', 'data/staging/')
    log.info("Staging materializado", extra={"run_id": RUN_ID})


@task(name="Run Mart")
def run_mart():
    run_model('mart_credit_features', 'data/marts/')
    log.info("Mart materializado", extra={"run_id": RUN_ID})


@task(name="Run Tests")
def run_tests():
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/', '-v'],
        capture_output=True, text=True
    )
    passed = r.returncode == 0
    log.info("Testes executados", extra={"run_id": RUN_ID, "passed": passed})
    if not passed:
        log.error("Testes falharam", extra={"run_id": RUN_ID, "output": r.stdout})
        raise Exception("Testes falharam — pipeline abortado")


@task(name="Monitor")
def monitor():
    import pandas as pd
    df = pd.read_parquet('data/marts/mart_credit_features.parquet')
    metrics = collect_metrics(df, RUN_ID)
    save_metrics(metrics, METRICS_PATH)
    drift = detect_drift(METRICS_PATH)
    if drift.get("drift_detected"):
        log.warning("Drift detectado", extra={"run_id": RUN_ID, **drift})
    else:
        log.info("Sem drift detectado", extra={"run_id": RUN_ID, **drift})
    return drift


@flow(name="Credit Intelligence Pipeline")
def credit_pipeline():
    df = ingest_csv()
    validate(df)
    fetch_api()
    merge()
    run_staging()
    run_mart()
    run_tests()
    monitor()


if __name__ == "__main__":
    credit_pipeline()
