"""
M5 Forecasting – Batch Inference DAG

Runs a self-contained batch prediction pipeline (no FastAPI dependency):
  1. run_batch_inference  – Re-generates h=28 forecasts for all series
  2. monitor_predictions  – Validates output and prints summary statistics

Schedule: daily (generates fresh 28-day rolling forecasts each run).

Author: Israel Igietsemhe
"""

import sys
sys.path.append("/opt/airflow/scripts")

from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

PREDICTIONS = Path("/opt/airflow/data/predictions")
MODELS_DIR  = Path("/opt/airflow/models")

default_args = {
    "owner":      "airflow",
    "start_date": datetime(2025, 10, 30),
    "retries":    1,
}


# ── Task 1: Run batch inference ────────────────────────────────────────────

def task_run_batch_inference():
    """
    Load saved LightGBM + StatsForecast models and generate new forecasts
    for all series.  Saves timestamped parquet + overwrites canonical
    m5_forecast.parquet.
    """
    from predict import run_batch_predict
    out_path = run_batch_predict(horizon=28, output_dir=PREDICTIONS)
    print(f"✅ Batch inference complete → {out_path}")
    return str(out_path)


# ── Task 2: Monitor / validate predictions ─────────────────────────────────

def task_monitor_predictions():
    """
    Read the latest forecast parquet and print validation stats.
    Raises if the file is missing or contains no rows.
    """
    import pandas as pd

    forecast_path = PREDICTIONS / "m5_forecast.parquet"
    if not forecast_path.exists():
        raise FileNotFoundError(
            f"Forecast file not found: {forecast_path}. "
            "Did the batch inference step complete successfully?"
        )

    df = pd.read_parquet(forecast_path)
    if df.empty:
        raise ValueError("Forecast parquet is empty.")

    model_cols = [c for c in df.columns if c not in ["unique_id", "ds"]]

    print(f"\n── Batch Inference Monitor ─────────────────────────────")
    print(f"   Forecast file : {forecast_path}")
    print(f"   Total rows    : {len(df):,}")
    print(f"   Series        : {df['unique_id'].nunique():,}")
    print(f"   Date range    : {df['ds'].min().date()} → {df['ds'].max().date()}")
    print(f"   Models        : {model_cols}")

    for col in model_cols:
        vals = df[col].dropna()
        neg  = (vals < 0).sum()
        null = df[col].isna().sum()
        print(
            f"\n   [{col}]\n"
            f"     mean={vals.mean():.2f}  median={vals.median():.2f}  "
            f"std={vals.std():.2f}\n"
            f"     min={vals.min():.2f}  max={vals.max():.2f}  "
            f"negatives={neg}  nulls={null}"
        )

    # Warn if metrics are stale
    metrics_path = MODELS_DIR / "model_metrics.json"
    if metrics_path.exists():
        import json
        metrics = json.loads(metrics_path.read_text())
        print(f"\n── Trained Model Metrics ────────────────────────────────")
        for m in metrics:
            print(f"   {m['model']:<40s}  RMSE={m['RMSE']}  MAE={m['MAE']}  SMAPE={m['SMAPE']}")
    else:
        print("⚠  model_metrics.json not found — run training pipeline to generate metrics")

    print(f"\n✅ Monitoring complete")


# ── DAG definition ─────────────────────────────────────────────────────────

with DAG(
    dag_id="m5_batch_inference",
    description="Daily batch predictions using trained StatsForecast + LightGBM models",
    default_args=default_args,
    schedule="@daily",
    catchup=False,
    tags=["m5", "inference", "batch"],
) as dag:

    infer = PythonOperator(
        task_id="run_batch_inference",
        python_callable=task_run_batch_inference,
    )

    monitor = PythonOperator(
        task_id="monitor_predictions",
        python_callable=task_monitor_predictions,
    )

    infer >> monitor
