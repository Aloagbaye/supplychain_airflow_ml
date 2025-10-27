from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime


def dummy_task():
    print("Starting supply chain ML pipeline")


default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 1, 1),
    'retries': 1
}

with DAG(
    'demand_forecasting_pipeline',
    default_args=default_args,
    description='ML pipeline for Walmart M5 forecasting',
    schedule_interval='@weekly',
    catchup=False,
    tags=['supply_chain', 'forecasting']
) as dag:

    start = PythonOperator(
        task_id='start_pipeline',
        python_callable=dummy_task
    )

    start
