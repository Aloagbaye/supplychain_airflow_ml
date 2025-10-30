import os
import pandas as pd
from pathlib import Path

RAW_PATH = Path("data/raw")
PROCESSED_PATH = Path("data/processed")

NUMBER_OF_ITEMS = 10

def preprocess_m5(sample_size: int = NUMBER_OF_ITEMS):
    print("🚀 Starting M5 preprocessing (sampled subset)...")

    # --- Load data ---
    sales = pd.read_csv(RAW_PATH / "sales_train_validation.csv")
    calendar = pd.read_csv(RAW_PATH / "calendar.csv")
    prices = pd.read_csv(RAW_PATH / "sell_prices.csv")

    # --- Limit to a few items for fast processing ---
    unique_items = sales["item_id"].unique()[:sample_size]
    sales = sales[sales["item_id"].isin(unique_items)]

    print(f"Selected {len(unique_items)} items out of {sales['item_id'].nunique()} total.")

    # --- Reshape sales data ---
    sales_melted = sales.melt(
        id_vars=["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"],
        var_name="day",
        value_name="demand"
    )

    # --- Merge with calendar ---
    data = sales_melted.merge(
        calendar[["d", "date", "wm_yr_wk", "weekday", "month", "year"]],
        left_on="day", right_on="d", how="left"
    ).drop(columns=["d"])

    # --- Merge with prices ---
    data = data.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left")

    # --- Feature engineering ---
    data["date"] = pd.to_datetime(data["date"])
    data["day_of_week"] = data["date"].dt.dayofweek
    data["is_weekend"] = data["day_of_week"].isin([5, 6]).astype(int)

    # --- Save subset ---
    PROCESSED_PATH.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_PATH / "m5_processed.parquet"
    data.to_parquet(output_path, index=False)

    print(f"✅ Saved processed dataset → {output_path}")
    print(f"Rows: {len(data):,}, Columns: {len(data.columns)}")

if __name__ == "__main__":
    preprocess_m5(sample_size=NUMBER_OF_ITEMS)
