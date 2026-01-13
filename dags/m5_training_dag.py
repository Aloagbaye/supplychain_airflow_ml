"""
M5 Forecasting – Model Training DAG
Author: Israel Igietsemhe
Version: 1.0
Description:
  Loads preprocessed M5 data, trains a baseline forecasting model,
  evaluates metrics, and saves predictions to /opt/airflow/data/predictions/.
"""

from datetime import datetime
import os
import pandas as pd
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from statsforecast import StatsForecast
from statsforecast.models import SimpleExponentialSmoothingOptimized


# ---------- CONFIGURATION ----------
DATA_DIR = "/opt/airflow/data"
PROCESSED_PATH = os.path.join(DATA_DIR, "processed", "m5_processed_nixtla.parquet")
INTERMEDIATE_DIR = os.path.join(DATA_DIR, "intermediate")
PREDICTIONS_DIR = os.path.join(DATA_DIR, "predictions")
DEPLOY_DIR = os.path.join(DATA_DIR, "deployed")

os.makedirs(INTERMEDIATE_DIR, exist_ok=True)
os.makedirs(PREDICTIONS_DIR, exist_ok=True)
os.makedirs(DEPLOY_DIR, exist_ok=True)


# ---------- DEFAULT ARGS ----------
default_args = {
    "owner": "airflow",
    "start_date": datetime(2025, 10, 30),
    "retries": 1,
    "depends_on_past": False,
}

# ---------- DAG DEFINITION ----------
dag = DAG(
    dag_id="m5_training_pipeline",
    description="Train, evaluate, and deploy M5 forecasting model",
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=["m5", "forecasting", "training"],
)


# ---------- TASK FUNCTIONS ----------

def load_preprocessed_data(sample_rows: int = 200_000):
    if not os.path.exists(PROCESSED_PATH):
        raise FileNotFoundError(f"Processed file not found at {PROCESSED_PATH}")

    df = pd.read_parquet(PROCESSED_PATH)
    # Sanity checks for Nixtla schema
    req = {"unique_id","ds","y"}
    if not req.issubset(df.columns):
        raise ValueError(f"Expected columns {req}, got {set(df.columns)}")

    # Optional: subsample to speed up baseline runs
    if sample_rows:
        df = df.groupby("unique_id", group_keys=False).head(500)  # ~500 days per id
        df = df.head(sample_rows)

    print(f"✅ Loaded Nixtla-format data: rows={len(df):,}, "
          f"series={df['unique_id'].nunique():,}, dates={df['ds'].min()} → {df['ds'].max()}")

    os.makedirs(INTERMEDIATE_DIR, exist_ok=True)
    df.to_parquet(os.path.join(INTERMEDIATE_DIR, "training_input.parquet"), index=False)
    print(f"💾 Saved intermediate → {INTERMEDIATE_DIR}/training_input.parquet")


def train_forecast_model():
    input_pq = os.path.join(INTERMEDIATE_DIR, "training_input.parquet")
    if not os.path.exists(input_pq):
        raise FileNotFoundError("Training input parquet not found.")

    df = pd.read_parquet(input_pq)

    # Ensure correct dtypes
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0)

    from statsforecast import StatsForecast
    from statsforecast.models import SimpleExponentialSmoothingOptimized

    sf = StatsForecast(models=[SimpleExponentialSmoothingOptimized()], freq="D", n_jobs=-1)
    sf.fit(df = df)
    forecasts = sf.predict(h=28)

    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
    out = os.path.join(PREDICTIONS_DIR, "m5_forecast.parquet")
    forecasts.to_parquet(out)
    print(f"✅ Forecast saved: {out}")


def evaluate_model():
    """Evaluate model results and print summary metrics."""
    preds_path = os.path.join(PREDICTIONS_DIR, "m5_forecast.parquet")
    if not os.path.exists(preds_path):
        raise FileNotFoundError("Predictions file not found for evaluation.")

    preds = pd.read_parquet(preds_path)
    #num_items = preds["unique_id"].nunique()
    #print(f"📊 Predictions generated for {num_items} unique items.")
    print(preds.head(5))  # preview


def deploy_predictions():
    """Simulate deployment by copying predictions to /data/deployed."""
    src = os.path.join(PREDICTIONS_DIR, "m5_forecast.parquet")
    dst = os.path.join(DEPLOY_DIR, "m5_forecast.parquet")

    if not os.path.exists(src):
        raise FileNotFoundError("No predictions file found to deploy.")

    os.system(f"cp {src} {dst}")
    print(f"🚀 Deployed forecast → {dst}")


# ---------- AIRFLOW OPERATORS ----------
load_data = PythonOperator(
    task_id="load_data",
    python_callable=load_preprocessed_data,
    dag=dag,
)

train_model = PythonOperator(
    task_id="train_model",
    python_callable=train_forecast_model,
    dag=dag,
)

evaluate = PythonOperator(
    task_id="evaluate_model",
    python_callable=evaluate_model,
    dag=dag,
)

deploy = PythonOperator(
    task_id="deploy_predictions",
    python_callable=deploy_predictions,
    dag=dag,
)


# ---------- TASK DEPENDENCIES ----------
load_data >> train_model >> evaluate >> deploy
