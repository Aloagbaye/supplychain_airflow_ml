"""
M5 Forecasting – Streamlit Monitoring Dashboard

Reads the latest forecast parquet and displays:
  - Forecast series plot for a selected item
  - Model comparison table (RMSE / MAE / SMAPE)
  - Summary statistics across all series

Mount /opt/airflow/data/predictions into the container at /data/predictions
and /opt/airflow/models at /data/models.
"""

import json
import os

import pandas as pd
import streamlit as st

FORECAST_PATH = "/data/predictions/m5_forecast.parquet"
METRICS_PATH  = "/data/models/model_metrics.json"

st.set_page_config(
    page_title="M5 Forecast Dashboard",
    page_icon="📦",
    layout="wide",
)

st.title("📦 M5 Supply Chain Forecast Dashboard")

# ── Load data ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_forecasts():
    if not os.path.exists(FORECAST_PATH):
        return pd.DataFrame()
    df = pd.read_parquet(FORECAST_PATH)
    df["ds"] = pd.to_datetime(df["ds"])
    return df


@st.cache_data(ttl=300)
def load_metrics():
    if not os.path.exists(METRICS_PATH):
        return pd.DataFrame()
    return pd.read_json(METRICS_PATH)


forecasts = load_forecasts()
metrics   = load_metrics()

if forecasts.empty:
    st.warning(
        "No forecast data found. "
        "Run **m5_training_pipeline** or **m5_batch_inference** in Airflow first."
    )
    st.stop()

model_cols = [c for c in forecasts.columns if c not in ["unique_id", "ds"]]
all_ids    = sorted(forecasts["unique_id"].unique().tolist())

# ── Sidebar ────────────────────────────────────────────────────────────────

st.sidebar.header("Controls")
selected_id = st.sidebar.selectbox("Select Item (unique_id)", all_ids)
selected_models = st.sidebar.multiselect(
    "Models to display", model_cols, default=model_cols
)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()

# ── KPI row ────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)
col1.metric("Total Series", f"{forecasts['unique_id'].nunique():,}")
col2.metric("Forecast Horizon", f"{forecasts['ds'].nunique()} days")
col3.metric("Models", len(model_cols))

st.markdown("---")

# ── Forecast chart ─────────────────────────────────────────────────────────

st.subheader(f"📈 Forecast: {selected_id}")
item_df = forecasts[forecasts["unique_id"] == selected_id].sort_values("ds")

if item_df.empty:
    st.warning("No data for selected item.")
else:
    chart_df = item_df[["ds"] + [m for m in selected_models if m in item_df.columns]]
    chart_df = chart_df.set_index("ds")
    st.line_chart(chart_df)

    with st.expander("Raw forecast data"):
        st.dataframe(item_df.reset_index(drop=True))

st.markdown("---")

# ── Model comparison ────────────────────────────────────────────────────────

st.subheader("🏆 Model Comparison (Holdout Evaluation)")

if not metrics.empty:
    best_model = metrics.sort_values("RMSE").iloc[0]["model"]
    st.dataframe(
        metrics.sort_values("RMSE").style.highlight_min(subset=["RMSE", "MAE", "SMAPE"], color="#d4edda"),
        use_container_width=True,
    )
    st.success(f"Best model by RMSE: **{best_model}**")
else:
    st.info("No evaluation metrics found. Run the training pipeline to generate metrics.")

st.markdown("---")

# ── Summary stats ───────────────────────────────────────────────────────────

st.subheader("📊 Forecast Distribution Summary")

summary_rows = []
for col in model_cols:
    vals = forecasts[col].dropna()
    summary_rows.append({
        "Model":  col,
        "Mean":   round(vals.mean(),   2),
        "Median": round(vals.median(), 2),
        "Std":    round(vals.std(),    2),
        "Min":    round(vals.min(),    2),
        "Max":    round(vals.max(),    2),
        "Nulls":  int(forecasts[col].isna().sum()),
    })

st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)
