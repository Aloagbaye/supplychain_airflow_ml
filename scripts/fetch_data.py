import pandas as pd
import os

RAW_PATH = "data/raw/sales_train_validation.csv"
OUT_PATH = "data/intermediate/sales_subset.csv"

def fetch_data():
    print("[INFO] Loading raw M5 data...")
    df = pd.read_csv(RAW_PATH)

    # Optional: Filter to 1 store and 10 products for faster dev
    df = df[df['store_id'] == 'CA_1'].iloc[:10]

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"[INFO] Saved subset to {OUT_PATH}")
