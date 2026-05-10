"""
M5 Forecasting – Batch Prediction Script

Loads saved model artifacts and generates h-step-ahead forecasts for all
series in the processed dataset.

Usage (standalone):
    python scripts/predict.py [--horizon 28] [--output data/predictions]

Called by:
    - dags/m5_batch_inference_dag.py
    - scripts/predict_service.py  (for on-demand series lookup)
"""

import argparse
import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR     = Path("/opt/airflow/data")
INTERMEDIATE = DATA_DIR / "intermediate"
PREDICTIONS  = DATA_DIR / "predictions"
MODELS_DIR   = Path("/opt/airflow/models")

LGBM_LAGS    = [7, 14, 21, 28]
LGBM_WINDOWS = [7, 14, 28]


# ── Loaders ────────────────────────────────────────────────────────────────

def load_series_data(sample_rows: int = 0) -> pd.DataFrame:
    """Load the preprocessed Nixtla-format parquet."""
    candidates = [
        INTERMEDIATE / "training_input.parquet",
        DATA_DIR / "processed" / "m5_processed_nixtla.parquet",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise FileNotFoundError(
            "No processed data found. Run the preprocessing DAG first."
        )
    df = pd.read_parquet(path)
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"], errors="coerce").fillna(0.0)
    df = df.sort_values(["unique_id", "ds"]).reset_index(drop=True)
    if sample_rows:
        df = df.head(sample_rows)
    print(f"Loaded  rows={len(df):,}  series={df['unique_id'].nunique():,}")
    return df


def load_statsforecast_model():
    """Load persisted StatsForecast object."""
    path = MODELS_DIR / "m5_statsforecast.pkl"
    if not path.exists():
        raise FileNotFoundError(
            f"StatsForecast model not found at {path}. Run training first."
        )
    return joblib.load(path)


def load_lgbm_artifact() -> dict:
    """Load LightGBM model + feature column list."""
    path = MODELS_DIR / "m5_lgbm.pkl"
    if not path.exists():
        raise FileNotFoundError(
            f"LightGBM artifact not found at {path}. Run training first."
        )
    return joblib.load(path)


# ── StatsForecast prediction ───────────────────────────────────────────────

def predict_statsforecast(
    df: pd.DataFrame,
    horizon: int = 28,
) -> pd.DataFrame:
    """
    Re-fit StatsForecast on the provided data and generate h-step forecasts.
    (StatsForecast objects store fitted state per series; re-fitting on
     potentially new/updated data ensures predictions are current.)
    """
    from statsforecast import StatsForecast
    from statsforecast.models import (
        Naive, SeasonalNaive, SimpleExponentialSmoothingOptimized,
        AutoETS, AutoTheta,
    )
    sf = StatsForecast(
        models=[
            Naive(),
            SeasonalNaive(season_length=7),
            SimpleExponentialSmoothingOptimized(),
            AutoETS(season_length=7),
            AutoTheta(season_length=7),
        ],
        freq="D",
        n_jobs=-1,
    )
    sf.fit(df=df)
    forecasts = sf.predict(h=horizon).reset_index()
    print(f"StatsForecast forecasts: {len(forecasts):,} rows")
    return forecasts


# ── LightGBM prediction ────────────────────────────────────────────────────

def predict_lgbm(
    df: pd.DataFrame,
    lgbm_artifact: dict,
    horizon: int = 28,
) -> pd.DataFrame:
    """
    Recursive multi-step forecast for all series using LightGBM.
    Each predicted value is fed back as lag input for subsequent steps.
    """
    model        = lgbm_artifact["model"]
    feature_cols = lgbm_artifact["feature_cols"]

    records = []
    for uid, grp in df.groupby("unique_id"):
        history = grp[["ds", "y"]].copy().sort_values("ds")
        last_ds = history["ds"].iloc[-1]

        for step in range(horizon):
            next_ds = last_ds + pd.Timedelta(days=step + 1)
            y_vals  = history["y"].values
            n       = len(y_vals)

            feat = {}
            for lag in LGBM_LAGS:
                feat[f"lag_{lag}"] = float(y_vals[-lag]) if n >= lag else 0.0
            for win in LGBM_WINDOWS:
                tail = y_vals[-(win + 1):-1] if n > win else y_vals
                feat[f"roll_mean_{win}"] = float(np.mean(tail)) if len(tail) > 0 else 0.0
            feat["dayofweek"] = next_ds.dayofweek
            feat["month"]     = next_ds.month
            feat["day"]       = next_ds.day

            x_row = pd.DataFrame([feat])[feature_cols].values
            yhat  = float(max(0.0, model.predict(x_row)[0]))
            records.append({"unique_id": uid, "ds": next_ds, "LGBMForecast": yhat})

            history = pd.concat(
                [history, pd.DataFrame({"ds": [next_ds], "y": [yhat]})],
                ignore_index=True,
            )

    df_out = pd.DataFrame(records)
    print(f"LightGBM forecasts: {len(df_out):,} rows")
    return df_out


# ── Save predictions ───────────────────────────────────────────────────────

def save_predictions(
    sf_forecasts: pd.DataFrame,
    lgbm_forecasts: pd.DataFrame,
    output_dir: Path = PREDICTIONS,
    timestamp: bool = False,
) -> Path:
    """Merge all model forecasts and write to parquet."""
    output_dir.mkdir(parents=True, exist_ok=True)

    combined = sf_forecasts.merge(lgbm_forecasts, on=["unique_id", "ds"], how="outer")

    fname = "m5_forecast.parquet"
    if timestamp:
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"m5_forecast_{ts}.parquet"

    out_path = output_dir / fname
    combined.to_parquet(out_path, index=False)
    print(f"✅ Predictions saved → {out_path}  shape={combined.shape}")
    return out_path


# ── Summary stats ──────────────────────────────────────────────────────────

def print_forecast_summary(forecast_df: pd.DataFrame) -> None:
    """Print a quick statistical summary of the generated forecasts."""
    model_cols = [c for c in forecast_df.columns if c not in ["unique_id", "ds"]]
    print("\n── Forecast Summary ──────────────────────────────────")
    for col in model_cols:
        vals = forecast_df[col].dropna()
        print(
            f"  {col:<40s}  "
            f"mean={vals.mean():.2f}  "
            f"median={vals.median():.2f}  "
            f"std={vals.std():.2f}  "
            f"min={vals.min():.2f}  "
            f"max={vals.max():.2f}"
        )
    print(f"  Series: {forecast_df['unique_id'].nunique():,}   "
          f"Horizon rows: {len(forecast_df):,}")


# ── Main entry point ───────────────────────────────────────────────────────

def run_batch_predict(horizon: int = 28, output_dir: Path = PREDICTIONS) -> Path:
    """
    Full batch prediction pipeline:
      1. Load series data
      2. Generate StatsForecast predictions
      3. Generate LightGBM predictions
      4. Merge, summarise, and save
    Returns path to the saved parquet file.
    """
    print("=" * 60)
    print("M5 Forecasting — Batch Prediction")
    print("=" * 60)

    df = load_series_data()

    print("\n[1/2] Running StatsForecast models...")
    sf_forecasts = predict_statsforecast(df, horizon=horizon)

    print("\n[2/2] Running LightGBM recursive forecast...")
    lgbm_art     = load_lgbm_artifact()
    lgbm_forecasts = predict_lgbm(df, lgbm_art, horizon=horizon)

    print_forecast_summary(
        sf_forecasts.merge(lgbm_forecasts, on=["unique_id", "ds"], how="outer")
    )

    out_path = save_predictions(
        sf_forecasts, lgbm_forecasts, output_dir=output_dir, timestamp=True
    )

    # Also overwrite the canonical latest-forecast file
    save_predictions(sf_forecasts, lgbm_forecasts, output_dir=output_dir, timestamp=False)

    print("\n✅ Batch prediction complete!")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run M5 batch predictions")
    parser.add_argument("--horizon",  type=int, default=28,         help="Forecast horizon in days")
    parser.add_argument("--output",   type=str, default=str(PREDICTIONS), help="Output directory")
    args = parser.parse_args()
    run_batch_predict(horizon=args.horizon, output_dir=Path(args.output))
