from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime
import pandas as pd
import requests, os, json

API_URL = "http://fastapi-service:8000/predict"
LOG_DIR = "/opt/airflow/outputs"

def trigger_batch_inference():
    payload = {"unique_id": "FOODS_3_CA_1", "horizon": 28}
    response = requests.post(API_URL, json=payload)
    print("Response:", response.text)
    return response.status_code

def monitor_predictions():
    df = pd.read_parquet(os.path.join(LOG_DIR, "predictions_log.parquet"))
    print(f"✅ Total predictions logged: {len(df)}")
    return df.tail(3).to_dict()

default_args = {"owner": "airflow", "start_date": datetime(2025, 10, 30)}

with DAG(
    "m5_batch_inference",
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    description="Run batch predictions from deployed FastAPI model",
) as dag:
    infer = PythonOperator(task_id="trigger_inference", python_callable=trigger_batch_inference)
    monitor = PythonOperator(task_id="monitor_predictions", python_callable=monitor_predictions)

    infer >> monitor
