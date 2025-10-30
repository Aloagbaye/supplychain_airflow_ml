import pandas as pd

INPUT_PATH = "data/intermediate/sales_clean.csv"
OUTPUT_PATH = "data/intermediate/sales_features.csv"

def feature_engineering():
    print("[INFO] Engineering features...")
    df = pd.read_csv(INPUT_PATH)

    # Example: Convert wide to long format for time series
    id_cols = ['id', 'item_id', 'dept_id', 'cat_id', 'store_id', 'state_id']
    df_long = df.melt(id_vars=id_cols, var_name="day", value_name="sales")

    # Lag feature
    df_long['lag_7'] = df_long.groupby('id')['sales'].shift(7)

    # Rolling mean
    df_long['rolling_mean_7'] = df_long.groupby('id')['sales'].transform(lambda x: x.shift(1).rolling(7).mean())

    df_long.to_csv(OUTPUT_PATH, index=False)
    print(f"[INFO] Features saved to {OUTPUT_PATH}")
