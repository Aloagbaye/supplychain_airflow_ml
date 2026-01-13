from fastapi import FastAPI
import pandas as pd
import joblib, uvicorn
from pydantic import BaseModel
import os, datetime

MODEL_PATH = "/opt/airflow/models/m5_best_model.pkl"
OUTPUT_PATH = "/opt/airflow/outputs"

app = FastAPI(title="M5 Forecast API", version="1.0")

class PredictRequest(BaseModel):
    unique_id: str
    horizon: int = 28

@app.on_event("startup")
def load_model():
    global model
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError("Model not found — please train first.")
    model = joblib.load(MODEL_PATH)
    os.makedirs(OUTPUT_PATH, exist_ok=True)
    print("✅ Model loaded successfully")

@app.post("/predict")
def predict(req: PredictRequest):
    # Generate dummy future dates for simplicity
    ds = pd.date_range(datetime.date.today(), periods=req.horizon, freq="D")
    forecast = [float(model["mean_forecast"])] * req.horizon  # example
    df = pd.DataFrame({"unique_id": req.unique_id, "ds": ds, "yhat": forecast})

    # Log predictions
    log_path = os.path.join(OUTPUT_PATH, "predictions_log.parquet")
    existing = pd.read_parquet(log_path) if os.path.exists(log_path) else pd.DataFrame()
    all_preds = pd.concat([existing, df])
    all_preds.to_parquet(log_path, index=False)

    return {"status": "ok", "rows": len(df), "saved_to": log_path}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)