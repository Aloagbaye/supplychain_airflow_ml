import os
import pandas as pd
from pathlib import Path

RAW = Path("/opt/airflow/data/raw")
OUT = Path("/opt/airflow/data/processed")
OUT.mkdir(parents=True, exist_ok=True)

def preprocess_m5(sample_items: int = 1000):
    print("🚀 Starting M5 preprocessing → Nixtla long format (unique_id, ds, y)")

    # Load raw CSVs
    sales = pd.read_csv(RAW / "sales_train_validation.csv")
    calendar = pd.read_csv(RAW / "calendar.csv")  # contains mapping d -> date
    # prices not needed for baseline; keep if you need future features:
    # prices = pd.read_csv(RAW / "sell_prices.csv")

    # Limit items for speed
    item_ids = sales["item_id"].unique()[:sample_items]
    sales = sales[sales["item_id"].isin(item_ids)].copy()

    # Melt daily columns (d_1 ... d_1913) to long
    id_cols = ["id","item_id","dept_id","cat_id","store_id","state_id"]
    long = sales.melt(
        id_vars=id_cols,
        var_name="d",
        value_name="y"  # rename demand -> y for Nixtla
    )

    # Map d -> date and rename to ds
    cal = calendar[["d","date"]].rename(columns={"date":"ds"})
    long = long.merge(cal, on="d", how="left").drop(columns=["d"])

    # Build Nixtla schema
    long = long.rename(columns={"item_id":"unique_id"})
    long["ds"] = pd.to_datetime(long["ds"])
    # Ensure numeric
    long["y"] = pd.to_numeric(long["y"], errors="coerce").fillna(0)

    # (Optional) keep only needed columns for StatsForecast
    nixtla_df = long[["unique_id","ds","y"]].sort_values(["unique_id","ds"])

    # Save final parquet
    out_path = OUT / "m5_processed_nixtla.parquet"
    nixtla_df.to_parquet(out_path, index=False)
    print(f"✅ Saved Nixtla-ready data → {out_path} | rows={len(nixtla_df):,}")

if __name__ == "__main__":
    preprocess_m5(sample_items=1000)
