"""
Airflow Sanity Test DAG
Purpose: Quickly verify Airflow DAG execution, permissions, and logging.
Author: Israel Igietsemhe
Version: 1.0
"""

from datetime import datetime
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
import os
import pandas as pd


# ---------- CONFIG ----------
BASE_DIR = "/opt/airflow/data"
TEST_DIR = os.path.join(BASE_DIR, "test")
os.makedirs(TEST_DIR, exist_ok=True)

default_args = {
    "owner": "airflow",
    "start_date": datetime(2025, 10, 30),
    "depends_on_past": False,
    "retries": 0,
}

dag = DAG(
    dag_id="test_training_dag",
    description="Quick DAG to verify Airflow environment and permissions",
    schedule=None,
    catchup=False,
    default_args=default_args,
    tags=["test", "airflow", "sanity"],
)


# ---------- TASK FUNCTIONS ----------

def check_permissions():
    """Check if Airflow user can write to /opt/airflow/data"""
    test_file = os.path.join(TEST_DIR, "permission_test.txt")
    with open(test_file, "w") as f:
        f.write("✅ Airflow can write to this directory.\n")
    print(f"Permission test successful → {test_file}")


def generate_mock_data():
    """Create a small synthetic dataset for training simulation."""
    df = pd.DataFrame({
        "unique_id": [f"item_{i}" for i in range(5)],
        "ds": pd.date_range("2024-01-01", periods=5, freq="D"),
        "y": [10, 12, 9, 14, 13],
    })
    file_path = os.path.join(TEST_DIR, "mock_data.csv")
    df.to_csv(file_path, index=False)
    print(f"✅ Generated mock dataset → {file_path}")


def simulate_model_training():
    """Simulate a 'training' step."""
    print("🧠 Simulating model training...")
    print("Training complete — accuracy=0.95, loss=0.12")


def validate_results():
    """Check if previous steps completed successfully."""
    files = os.listdir(TEST_DIR)
    print("📁 Files in /test directory:", files)
    if not any("mock_data.csv" in f for f in files):
        raise FileNotFoundError("mock_data.csv not found!")
    print("✅ DAG validation successful.")


# ---------- AIRFLOW OPERATORS ----------
check = PythonOperator(
    task_id="check_permissions",
    python_callable=check_permissions,
    dag=dag,
)

generate = PythonOperator(
    task_id="generate_mock_data",
    python_callable=generate_mock_data,
    dag=dag,
)

train = PythonOperator(
    task_id="simulate_training",
    python_callable=simulate_model_training,
    dag=dag,
)

validate = PythonOperator(
    task_id="validate_results",
    python_callable=validate_results,
    dag=dag,
)


# ---------- DEPENDENCIES ----------
check >> generate >> train >> validate
