"""
M5 Forecasting – Model Training Script

Trains the following models:
  Statistical (StatsForecast):
    - Naive               : trivial last-value baseline
    - SeasonalNaive       : last observed same-weekday baseline
    - SES                 : SimpleExponentialSmoothingOptimized
    - AutoETS             : automatic Error/Trend/Seasonality selection
    - AutoTheta           : automatic Theta method
  ML (LightGBM):
    - LGBMForecast        : regression on lag + rolling-mean + calendar features

After training, a holdout evaluation (last 28 days per series) produces a
metrics table (RMSE / MAE / SMAPE) that is saved to models/model_metrics.json.
All forecasts are merged into data/predictions/m5_forecast.parquet.
"""

import json
import shutil
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from statsforecast import StatsForecast
from statsforecast.models import (
    Naive,
    SeasonalNaive,
    SimpleExponentialSmoothingOptimized,
    AutoETS,
    AutoTheta,
)

# ── Paths ──────────────────────────────────────────────────────────────────
DATA_DIR     = Path("/opt/airflow/data")
INTERMEDIATE = DATA_DIR / "intermediate"
PREDICTIONS  = DATA_DIR / "predictions"
MODELS_DIR   = Path("/opt/airflow/models")

for _d in [INTERMEDIATE, PREDICTIONS, MODELS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

HORIZON       = 28
SEASON_LENGTH = 7

SF_MODELS = [
    Naive(),
    SeasonalNaive(season_length=SEASON_LENGTH),
    SimpleExponentialSmoothingOptimized(),
    AutoETS(season_length=SEASON_LENGTH),
    AutoTheta(season_length=SEASON_LENGTH),
]

LGBM_LAGS    = [7, 14, 21, 28]
LGBM_WINDOWS = [7, 14, 28]


# ── Data loading ───────────────────────────────────────────────────────────

def load_training_data(sample_rows: int = 200_000) -> pd.DataFrame:
    """Load preprocessed Nixtla-format parquet and optionally subsample."""
    candidates = [
        INTERMEDIATE / "training_input.parquet",
        DATA_DIR / "processed" / "m5_processed_nixtla.parquet",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise FileNotFoundError(
            "Training data not found. Run the preprocessing DAG first.\n"
            f"Looked in: {candidates}"
        )

    df = pd.read_parquet(path)
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"], errors="coerce").fillna(0.0)

    # Keep at most 500 days per series, then cap total rows
    df = (
        df.groupby("unique_id", group_keys=False)
        .head(500)
        .head(sample_rows)
        .sort_values(["unique_id", "ds"])
        .reset_index(drop=True)
    )
    print(
        f"Loaded  rows={len(df):,}  series={df['unique_id'].nunique():,}  "
        f"dates={df['ds'].min().date()} → {df['ds'].max().date()}"
    )
    return df


# ── Feature engineering (LightGBM) ────────────────────────────────────────

def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag / rolling-mean / calendar features (in-place on a copy)."""
    df = df.copy()
    grp = df.groupby("unique_id")["y"]
    for lag in LGBM_LAGS:
        df[f"lag_{lag}"] = grp.shift(lag)
    for win in LGBM_WINDOWS:
        df[f"roll_mean_{win}"] = grp.transform(
            lambda x, w=win: x.shift(1).rolling(w, min_periods=1).mean()
        )
    df["dayofweek"] = df["ds"].dt.dayofweek
    df["month"]     = df["ds"].dt.month
    df["day"]       = df["ds"].dt.day
    return df


def _feature_cols(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c not in ["unique_id", "ds", "y"]]


# ── StatsForecast ──────────────────────────────────────────────────────────

def train_statsforecast(df: pd.DataFrame) -> tuple:
    """Fit StatsForecast models and produce h=28 forecasts."""
    sf = StatsForecast(models=SF_MODELS, freq="D", n_jobs=-1)
    sf.fit(df=df)
    forecasts = sf.predict(h=HORIZON).reset_index()
    print(f"StatsForecast  forecasts shape={forecasts.shape}")
    return sf, forecasts


def evaluate_statsforecast(df: pd.DataFrame) -> pd.DataFrame:
    """
    Last-28-day holdout evaluation for all StatsForecast models.
    Returns a DataFrame with columns: model, RMSE, MAE, SMAPE.
    """
    cutoff  = df.groupby("unique_id")["ds"].max() - pd.Timedelta(days=HORIZON)
    merged  = df.merge(cutoff.rename("cutoff").reset_index(), on="unique_id")
    train   = merged[merged["ds"] <= merged["cutoff"]][["unique_id", "ds", "y"]].copy()
    test    = merged[merged["ds"] >  merged["cutoff"]][["unique_id", "ds", "y"]].copy()

    if train.empty or test.empty:
        print("⚠  Not enough data for holdout evaluation")
        return pd.DataFrame()

    sf = StatsForecast(models=SF_MODELS, freq="D", n_jobs=-1)
    sf.fit(df=train)
    preds = sf.predict(h=HORIZON).reset_index()

    model_cols = [c for c in preds.columns if c not in ["unique_id", "ds"]]
    records = []
    for col in model_cols:
        ev = test.merge(preds[["unique_id", "ds", col]], on=["unique_id", "ds"], how="inner")
        if ev.empty:
            continue
        y_true = ev["y"].values
        y_hat  = ev[col].values
        rmse   = float(np.sqrt(np.mean((y_true - y_hat) ** 2)))
        mae    = float(np.mean(np.abs(y_true - y_hat)))
        denom  = (np.abs(y_true) + np.abs(y_hat)) / 2
        smape  = float(
            np.mean(np.where(denom > 0, np.abs(y_true - y_hat) / denom, 0.0)) * 100
        )
        records.append({
            "model": col,
            "RMSE":  round(rmse,  4),
            "MAE":   round(mae,   4),
            "SMAPE": round(smape, 4),
        })

    metrics_df = pd.DataFrame(records).sort_values("RMSE").reset_index(drop=True)
    print("\n── StatsForecast Holdout Evaluation (last 28 days) ──")
    print(metrics_df.to_string(index=False))
    return metrics_df


# ── LightGBM ───────────────────────────────────────────────────────────────

def train_lgbm(df: pd.DataFrame) -> tuple:
    """
    Train LightGBM regressor on lag/rolling features.
    Returns (model, feature_cols, eval_metrics_dict).
    """
    import lightgbm as lgb

    feat_df  = add_lag_features(df).dropna()
    f_cols   = _feature_cols(feat_df)
    X        = feat_df[f_cols].values
    y        = feat_df["y"].values

    # Simple time-based split for evaluation (last 10 %)
    split    = int(len(feat_df) * 0.90)
    X_tr, y_tr = X[:split], y[:split]
    X_te, y_te = X[split:], y[split:]

    model = lgb.LGBMRegressor(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        random_state=42,
        verbose=-1,
    )
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_te, y_te)],
        callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(period=-1)],
    )

    y_hat  = np.clip(model.predict(X_te), 0, None)
    rmse   = float(np.sqrt(np.mean((y_te - y_hat) ** 2)))
    mae    = float(np.mean(np.abs(y_te - y_hat)))
    denom  = (np.abs(y_te) + np.abs(y_hat)) / 2
    smape  = float(
        np.mean(np.where(denom > 0, np.abs(y_te - y_hat) / denom, 0.0)) * 100
    )
    metrics = {
        "model": "LGBMForecast",
        "RMSE":  round(rmse,  4),
        "MAE":   round(mae,   4),
        "SMAPE": round(smape, 4),
    }
    print(
        f"LightGBM  RMSE={metrics['RMSE']}  "
        f"MAE={metrics['MAE']}  SMAPE={metrics['SMAPE']}"
    )

    # Retrain on full data before returning
    model.fit(X, y, callbacks=[lgb.log_evaluation(period=-1)])
    print(f"LightGBM trained on {len(X):,} rows, {len(f_cols)} features")
    return model, f_cols, metrics


def lgbm_recursive_forecast(
    df: pd.DataFrame,
    model,
    feature_cols: list,
    horizon: int = HORIZON,
) -> pd.DataFrame:
    """
    Recursively predict `horizon` steps per series using the LightGBM model.
    Each new prediction is appended to the history before the next step.
    """
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
                tail   = y_vals[-(win + 1):-1] if n > win else y_vals
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

    return pd.DataFrame(records)


# ── Save artifacts ─────────────────────────────────────────────────────────

def save_artifacts(
    sf_model: StatsForecast,
    sf_forecasts: pd.DataFrame,
    lgbm_model,
    lgbm_feature_cols: list,
    lgbm_forecasts: pd.DataFrame,
    all_metrics: pd.DataFrame,
) -> None:
    """Persist all models, forecasts, and metrics to disk."""

    # Combined forecast parquet
    combined = sf_forecasts.merge(lgbm_forecasts, on=["unique_id", "ds"], how="outer")
    forecast_path = PREDICTIONS / "m5_forecast.parquet"
    combined.to_parquet(forecast_path, index=False)
    print(f"✅ Forecasts saved → {forecast_path}  shape={combined.shape}")

    # StatsForecast object
    sf_path = MODELS_DIR / "m5_statsforecast.pkl"
    joblib.dump(sf_model, sf_path)
    print(f"✅ StatsForecast model → {sf_path}")

    # LightGBM artifact (model + feature column list)
    if lgbm_model is not None:
        lgbm_artifact = {"model": lgbm_model, "feature_cols": lgbm_feature_cols}
        lgbm_path = MODELS_DIR / "m5_lgbm.pkl"
        joblib.dump(lgbm_artifact, lgbm_path)
        print(f"✅ LightGBM artifact → {lgbm_path}")

    # Metrics JSON
    if not all_metrics.empty:
        metrics_path = MODELS_DIR / "model_metrics.json"
        metrics_path.write_text(all_metrics.to_json(orient="records", indent=2))
        print(f"✅ Metrics → {metrics_path}")
        best = all_metrics.iloc[0]["model"]
        print(f"🏆 Best model by RMSE: {best}")

    # Legacy m5_best_model.pkl used by predict_service.py
    best_payload = {
        "sf":           sf_model,
        "lgbm":         lgbm_model,
        "lgbm_feature_cols": lgbm_feature_cols,
        "forecast_path": str(forecast_path),
    }
    joblib.dump(best_payload, MODELS_DIR / "m5_best_model.pkl")


# ── Main entry point ───────────────────────────────────────────────────────

def run_full_training(sample_rows: int = 200_000) -> pd.DataFrame:
    """
    End-to-end training pipeline.
    Returns a DataFrame of model evaluation metrics.
    """
    print("=" * 60)
    print("M5 Forecasting — Full Training Pipeline")
    print("=" * 60)

    df = load_training_data(sample_rows)

    # 1. Statistical models
    print("\n[1/4] Training StatsForecast models (Naive, SeasonalNaive, SES, AutoETS, AutoTheta)...")
    sf_model, sf_forecasts = train_statsforecast(df)

    # 2. Evaluate StatsForecast (holdout)
    print("\n[2/4] Evaluating StatsForecast models on last-28-day holdout...")
    sf_metrics = evaluate_statsforecast(df)

    # 3. LightGBM
    print("\n[3/4] Training LightGBM model...")
    lgbm_model, lgbm_feature_cols, lgbm_eval = train_lgbm(df)

    print("\n[3b/4] Generating LightGBM recursive forecasts (h=28)...")
    lgbm_forecasts = lgbm_recursive_forecast(df, lgbm_model, lgbm_feature_cols)

    # Combine metrics
    if not sf_metrics.empty:
        all_metrics = pd.concat(
            [sf_metrics, pd.DataFrame([lgbm_eval])], ignore_index=True
        ).sort_values("RMSE").reset_index(drop=True)
    else:
        all_metrics = pd.DataFrame([lgbm_eval])

    print("\n── Full Model Comparison ──")
    print(all_metrics.to_string(index=False))

    # 4. Save
    print("\n[4/4] Saving artifacts...")
    save_artifacts(sf_model, sf_forecasts, lgbm_model, lgbm_feature_cols, lgbm_forecasts, all_metrics)

    print("\n✅ Training complete!")
    return all_metrics


if __name__ == "__main__":
    run_full_training(sample_rows=200_000)
