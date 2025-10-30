import sys
sys.path.append("/opt/airflow/scripts")
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime
from preprocess import preprocess_m5


with DAG(
    dag_id="m5_preprocessing_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule="@once",
    catchup=False,
    tags=["m5", "preprocessing"]
) as dag:

    preprocess_task = PythonOperator(
        task_id="preprocess_m5_data",
        python_callable=preprocess_m5
    )
