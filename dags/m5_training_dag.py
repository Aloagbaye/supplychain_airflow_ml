"""
M5 Forecasting – Model Training DAG

Pipeline:
  1. load_data          – Load and subsample preprocessed parquet
  2. train_models       – StatsForecast (5 models) + LightGBM
  3. evaluate_models    – Holdout RMSE/MAE/SMAPE, print comparison table
  4. deploy_predictions – Copy forecasts to data/deployed/

Author: Israel Igietsemhe
"""

import sys
sys.path.append("/opt/airflow/scripts")

import shutil
from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

# ── Configuration ──────────────────────────────────────────────────────────
DATA_DIR     = Path("/opt/airflow/data")
INTERMEDIATE = DATA_DIR / "intermediate"
PREDICTIONS  = DATA_DIR / "predictions"
DEPLOY_DIR   = DATA_DIR / "deployed"
MODELS_DIR   = Path("/opt/airflow/models")

for _d in [INTERMEDIATE, PREDICTIONS, DEPLOY_DIR, MODELS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

default_args = {
    "owner":           "airflow",
    "start_date":      datetime(2025, 10, 30),
    "retries":         1,
    "depends_on_past": False,
}

dag = DAG(
    dag_id="m5_training_pipeline",
    description="Train, evaluate, and deploy M5 forecasting models (Stats + LightGBM)",
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=["m5", "forecasting", "training"],
)


# ── Task 1: Load data ──────────────────────────────────────────────────────

def task_load_data(sample_rows: int = 200_000):
    """Load preprocessed data, validate schema, save to intermediate."""
    import pandas as pd

    processed_path = DATA_DIR / "processed" / "m5_processed_nixtla.parquet"
    if not processed_path.exists():
        raise FileNotFoundError(
            f"Processed file not found at {processed_path}. "
            "Run the m5_preprocessing_pipeline DAG first."
        )

    df = pd.read_parquet(processed_path)

    required_cols = {"unique_id", "ds", "y"}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"Expected columns {required_cols}, got {set(df.columns)}")

    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"], errors="coerce").fillna(0.0)

    # Subsample: up to 500 days per series, then cap total
    df = (
        df.groupby("unique_id", group_keys=False)
        .head(500)
        .head(sample_rows)
        .sort_values(["unique_id", "ds"])
        .reset_index(drop=True)
    )

    out_path = INTERMEDIATE / "training_input.parquet"
    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    print(
        f"✅ Training data saved → {out_path}\n"
        f"   rows={len(df):,}  series={df['unique_id'].nunique():,}  "
        f"dates={df['ds'].min().date()} → {df['ds'].max().date()}"
    )


# ── Task 2: Train models ───────────────────────────────────────────────────

def task_train_models():
    """
    Train all models via train_model.run_full_training().
    Saves StatsForecast pkl, LightGBM pkl, combined forecast parquet, metrics JSON.
    """
    from train_model import run_full_training
    metrics = run_full_training(sample_rows=200_000)
    print(metrics.to_string(index=False))


# ── Task 3: Evaluate models ────────────────────────────────────────────────

def task_evaluate_models():
    """Print model metrics from the saved JSON and forecast statistics."""
    import json
    import pandas as pd

    metrics_path  = MODELS_DIR / "model_metrics.json"
    forecast_path = PREDICTIONS / "m5_forecast.parquet"

    if metrics_path.exists():
        metrics = pd.read_json(metrics_path)
        print("\n══ Model Evaluation Results ══════════════════════════════")
        print(metrics.sort_values("RMSE").to_string(index=False))
        best = metrics.sort_values("RMSE").iloc[0]
        print(f"\n🏆 Best model: {best['model']}  "
              f"RMSE={best['RMSE']}  MAE={best['MAE']}  SMAPE={best['SMAPE']}")
    else:
        print("⚠  Metrics file not found; skipping metrics display")

    if forecast_path.exists():
        forecasts = pd.read_parquet(forecast_path)
        model_cols = [c for c in forecasts.columns if c not in ["unique_id", "ds"]]
        print(f"\n── Forecast Summary ({len(forecasts):,} rows, "
              f"{forecasts['unique_id'].nunique():,} series) ──")
        for col in model_cols:
            vals = forecasts[col].dropna()
            print(
                f"  {col:<40s}  "
                f"mean={vals.mean():.2f}  "
                f"std={vals.std():.2f}  "
                f"min={vals.min():.2f}  "
                f"max={vals.max():.2f}"
            )
    else:
        print("⚠  Forecast parquet not found; skipping forecast summary")


# ── Task 4: Deploy predictions ─────────────────────────────────────────────

def task_deploy_predictions():
    """Copy forecasts and model artifacts to data/deployed/ for serving."""
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)

    files_to_deploy = {
        PREDICTIONS / "m5_forecast.parquet": DEPLOY_DIR / "m5_forecast.parquet",
        MODELS_DIR  / "model_metrics.json":  DEPLOY_DIR / "model_metrics.json",
    }

    for src, dst in files_to_deploy.items():
        if not src.exists():
            raise FileNotFoundError(f"Source file not found: {src}")
        shutil.copy2(src, dst)
        print(f"✅ Deployed {src.name} → {dst}")

    print(f"🚀 All artifacts deployed to {DEPLOY_DIR}")


# ── Operators ──────────────────────────────────────────────────────────────

load_data = PythonOperator(
    task_id="load_data",
    python_callable=task_load_data,
    dag=dag,
)

train_models = PythonOperator(
    task_id="train_models",
    python_callable=task_train_models,
    dag=dag,
)

evaluate_models = PythonOperator(
    task_id="evaluate_models",
    python_callable=task_evaluate_models,
    dag=dag,
)

deploy_predictions = PythonOperator(
    task_id="deploy_predictions",
    python_callable=task_deploy_predictions,
    dag=dag,
)

# ── Dependencies ───────────────────────────────────────────────────────────
load_data >> train_models >> evaluate_models >> deploy_predictions
