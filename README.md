# Supply Chain ML with Apache Airflow

An end-to-end machine learning pipeline for supply chain demand forecasting using the [M5 Forecasting dataset](https://www.kaggle.com/c/m5-forecasting-accuracy) (Walmart retail sales). Apache Airflow 3.1.0 orchestrates preprocessing, multi-model training, and daily batch inference. A FastAPI service and Streamlit dashboard expose results.

## Features

- **Multi-model forecasting**: 5 statistical models + LightGBM trained and compared automatically
- **Automated evaluation**: holdout RMSE / MAE / SMAPE comparison table saved to `models/model_metrics.json`
- **Batch inference**: daily Airflow DAG refreshes 28-day rolling forecasts for all series
- **REST API**: FastAPI serves pre-computed forecasts with item lookup and model filtering
- **Monitoring dashboard**: Streamlit visualises forecasts, model rankings, and distribution stats
- **Containerised**: single `docker-compose up` starts every service

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Docker Compose                                             │
│                                                             │
│  ┌──────────┐   ┌──────────────┐   ┌───────────────────┐  │
│  │PostgreSQL│◄──│Airflow       │   │Airflow Scheduler  │  │
│  │(metadata)│   │API Server    │   │(runs DAGs)        │  │
│  │          │   │:8081         │   │                   │  │
│  └──────────┘   └──────────────┘   └─────────┬─────────┘  │
│                                               │             │
│            ┌──────────────────────────────────┘             │
│            ▼                                                │
│  ┌─────────────────┐   ┌──────────────┐  ┌──────────────┐ │
│  │ data/processed/ │──►│ data/        │  │ models/      │ │
│  │ (parquet)       │   │ predictions/ │  │ *.pkl        │ │
│  └─────────────────┘   └──────┬───────┘  └──────┬───────┘ │
│                                │                 │          │
│                      ┌─────────▼──────┐  ┌──────▼───────┐ │
│                      │FastAPI Service │  │Streamlit     │ │
│                      │:8000           │  │Dashboard :8501│ │
│                      └────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Services

| Service | Port | Description |
|---|---|---|
| PostgreSQL | — | Airflow metadata database |
| Airflow API Server | 8081 | Web UI + REST API for DAG management |
| Airflow Scheduler | — | Executes DAG tasks |
| FastAPI Service | 8000 | Serves pre-computed forecasts on demand |
| Streamlit Dashboard | 8501 | Interactive forecast monitoring |

---

## Models Trained

| Model | Type | Library |
|---|---|---|
| `Naive` | Statistical baseline | StatsForecast |
| `SeasonalNaive` | Weekly seasonal baseline | StatsForecast |
| `SimpleExponentialSmoothingOptimized` | Exponential smoothing | StatsForecast |
| `AutoETS` | Automatic Error/Trend/Seasonality | StatsForecast |
| `AutoTheta` | Automatic Theta method | StatsForecast |
| `LGBMForecast` | Gradient boosting with lag features | LightGBM |

LightGBM uses lag-7/14/21/28, rolling-mean-7/14/28, and calendar (day-of-week, month, day) features. All models are evaluated against a last-28-day holdout; metrics are saved to `models/model_metrics.json`.

---

## Project Structure

```
supplychain_airflow_ml/
├── dags/
│   ├── m5_preprocessing_dag.py    # Wide → long format conversion (run once)
│   ├── m5_training_dag.py         # Multi-model training + evaluation + deploy
│   ├── m5_batch_inference_dag.py  # Daily batch forecast refresh
│   └── test_training_dag.py       # Airflow environment sanity check
├── scripts/
│   ├── preprocess.py              # M5 → Nixtla long format
│   ├── train_model.py             # All model training logic (stats + LightGBM)
│   ├── predict.py                 # Batch prediction using saved models
│   ├── predict_service.py         # FastAPI application
│   ├── dashboard.py               # Streamlit monitoring dashboard
│   └── feature_engineering.py     # Standalone lag/rolling feature builder
├── data/
│   ├── raw/                       # M5 CSV files (user-supplied)
│   ├── processed/                 # m5_processed_nixtla.parquet
│   ├── intermediate/              # training_input.parquet (sampled)
│   ├── predictions/               # m5_forecast.parquet (all models)
│   └── deployed/                  # Copy promoted by training DAG
├── models/
│   ├── m5_statsforecast.pkl       # Fitted StatsForecast object
│   ├── m5_lgbm.pkl                # LightGBM model + feature column list
│   ├── m5_best_model.pkl          # Combined artifact used by FastAPI
│   └── model_metrics.json         # RMSE / MAE / SMAPE per model
├── outputs/                       # predictions_log.parquet (API call log)
├── plugins/                       # Airflow plugins (empty by default)
├── Dockerfile                     # Custom Airflow image with ML dependencies
├── docker-compose.yml             # All services
└── requirements.txt               # Python dependencies
```

---

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- At least 8 GB RAM allocated to Docker
- M5 dataset CSV files placed in `data/raw/`:
  - `sales_train_validation.csv` — required
  - `calendar.csv` — required
  - `sell_prices.csv` — optional (not used in baseline)

Download from: https://www.kaggle.com/c/m5-forecasting-accuracy/data

---

## Quick Start (Docker)

### 1. Clone and prepare data

```bash
git clone <repository-url>
cd supplychain_airflow_ml

# Place M5 CSVs
cp /path/to/m5/sales_train_validation.csv data/raw/
cp /path/to/m5/calendar.csv               data/raw/
```

### 2. Create environment file

```bash
# .env (Linux/macOS — use your actual UID)
echo "AIRFLOW_UID=$(id -u)" > .env
echo "AIRFLOW_GID=0"       >> .env

# Windows PowerShell
"AIRFLOW_UID=50000`nAIRFLOW_GID=0" | Out-File .env -Encoding ascii
```

### 3. Build and start all services

```bash
docker-compose build
docker-compose up -d
```

### 4. Run the pipeline

Open **http://localhost:8081** (admin / admin) and trigger the DAGs in order:

| Step | DAG | Trigger |
|---|---|---|
| 1 | `m5_preprocessing_pipeline` | Manual — run once |
| 2 | `m5_training_pipeline` | Manual — run after preprocessing |
| 3 | `m5_batch_inference` | Runs automatically at midnight daily |

After step 2 completes the FastAPI service and Streamlit dashboard are ready.

---

## Running Services Locally (without Docker)

### Setup virtual environment

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows PowerShell
venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Run each script independently

```bash
# 1. Preprocess raw M5 data
python scripts/preprocess.py

# 2. Train all models (stats + LightGBM) and save artifacts
python scripts/train_model.py

# 3. Generate batch predictions from saved models
python scripts/predict.py --horizon 28 --output data/predictions
```

### Start the FastAPI service

```bash
uvicorn scripts.predict_service:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at **http://localhost:8000**.  
Interactive docs: **http://localhost:8000/docs**

> **Note**: The service reads from `data/predictions/m5_forecast.parquet`. Run the training script first, or it will return `503 Service Unavailable`.

### Start the Streamlit dashboard

```bash
streamlit run scripts/dashboard.py --server.port 8501
```

The dashboard will open at **http://localhost:8501**.

> **Note**: The dashboard reads the same `data/predictions/m5_forecast.parquet` and `models/model_metrics.json`. Run the training script first.

---

## FastAPI Reference

Base URL: `http://localhost:8000`

### `GET /health`

Returns service status and a count of loaded forecasts.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "series": 1000,
  "rows": 28000,
  "models": ["Naive", "SeasonalNaive", "SES", "AutoETS", "AutoTheta", "LGBMForecast"]
}
```

### `GET /items?limit=200`

List available `unique_id` values.

```bash
curl "http://localhost:8000/items?limit=10"
```

### `GET /models`

List forecast model columns and their evaluation metrics.

```bash
curl http://localhost:8000/models
```

### `POST /predict`

Retrieve forecasts for a specific item.

**Request body:**

```json
{
  "unique_id": "HOBBIES_1_001_CA_1_validation",
  "horizon": 28,
  "model": "AutoETS"
}
```

- `unique_id` — required; use `/items` to find valid IDs
- `horizon` — optional, 1–365 (default: 28)
- `model` — optional; omit to return all models

**Example:**

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"unique_id": "HOBBIES_1_001_CA_1_validation", "horizon": 28}'
```

**Response:**

```json
{
  "status": "ok",
  "unique_id": "HOBBIES_1_001_CA_1_validation",
  "rows": 28,
  "models": ["Naive", "SeasonalNaive", "SES", "AutoETS", "AutoTheta", "LGBMForecast"],
  "saved_to": "/opt/airflow/outputs/predictions_log.parquet"
}
```

### `POST /refresh`

Reload the forecast parquet from disk after a training run, without restarting the service.

```bash
curl -X POST http://localhost:8000/refresh
```

---

## Streamlit Dashboard

URL: **http://localhost:8501**

| Panel | Description |
|---|---|
| KPI row | Total series, forecast horizon, number of models |
| Forecast chart | Line chart of all model predictions for the selected item |
| Raw data expander | Scrollable table of the underlying forecast values |
| Model comparison | Sortable RMSE / MAE / SMAPE table with best model highlighted |
| Distribution summary | Mean, median, std, min, max across all series per model |

Use the sidebar to select an item and toggle which models to display. Click **Refresh data** to re-read the parquet without restarting.

---

## DAGs Reference

### `m5_preprocessing_pipeline`

Converts raw M5 CSV (wide format) to Nixtla long format.

- **Schedule**: `@once`
- **Tasks**:
  - `preprocess_m5_data` — melts `d_1 … d_1913` columns, joins calendar dates, outputs `data/processed/m5_processed_nixtla.parquet`
- **Tunable**: set `sample_items` in `scripts/preprocess.py` (default: 1000 items)

### `m5_training_pipeline`

Full training pipeline across all models.

- **Schedule**: `None` (manual trigger)
- **Tasks**:

| Task | What it does |
|---|---|
| `load_data` | Validates schema, subsamples to ≤500 days/series and ≤200k rows total, saves `data/intermediate/training_input.parquet` |
| `train_models` | Trains 5 StatsForecast models + LightGBM; saves model PKLs, combined forecast parquet, and metrics JSON |
| `evaluate_models` | Reads metrics JSON, prints ranked comparison table with best model highlighted |
| `deploy_predictions` | Copies `data/predictions/m5_forecast.parquet` and `models/model_metrics.json` to `data/deployed/` |

### `m5_batch_inference`

Daily refresh of 28-day rolling forecasts.

- **Schedule**: `@daily`
- **Tasks**:

| Task | What it does |
|---|---|
| `run_batch_inference` | Re-runs StatsForecast + LightGBM on current data; saves timestamped parquet and overwrites canonical `m5_forecast.parquet` |
| `monitor_predictions` | Validates output, prints per-model summary stats and negative/null counts |

### `test_training_dag`

Airflow environment sanity check (write permissions, imports, task execution). Run this first if Airflow is newly deployed.

---

## Configuration

### Environment variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `AIRFLOW_UID` | `50000` | UID for Airflow file permissions (use `id -u` on Linux) |
| `AIRFLOW_GID` | `0` | GID for Airflow file permissions |

### Sampling / speed tuning

| Setting | Location | Default | Effect |
|---|---|---|---|
| `sample_items` | `scripts/preprocess.py` line 9 | `1000` | Number of unique items to include in preprocessing |
| `sample_rows` | `scripts/train_model.py` → `run_full_training()` | `200_000` | Max rows fed to model training |
| `horizon` | `scripts/train_model.py` `HORIZON` | `28` | Forecast horizon in days |
| `SEASON_LENGTH` | `scripts/train_model.py` | `7` | Weekly seasonality assumed by SeasonalNaive / AutoETS / AutoTheta |

---

## Data Formats

### Raw input (M5)

Wide format — one row per item, one column per day:

| id | item_id | dept_id | store_id | d_1 | d_2 | … | d_1913 |
|---|---|---|---|---|---|---|---|

### Processed (Nixtla / StatsForecast)

Long format required by all models:

| Column | Type | Description |
|---|---|---|
| `unique_id` | string | Item identifier, e.g. `HOBBIES_1_001_CA_1_validation` |
| `ds` | datetime | Date of observation |
| `y` | float | Daily unit sales |

### Forecast output (`data/predictions/m5_forecast.parquet`)

| Column | Description |
|---|---|
| `unique_id` | Item identifier |
| `ds` | Forecast date |
| `Naive` | Naive model forecast |
| `SeasonalNaive` | Seasonal Naive forecast |
| `SES` | Simple Exponential Smoothing forecast |
| `AutoETS` | AutoETS forecast |
| `AutoTheta` | AutoTheta forecast |
| `LGBMForecast` | LightGBM forecast |

---

## Troubleshooting

### Services not starting

```bash
# Check all container statuses
docker-compose ps

# Check initialisation logs
docker-compose logs airflow-init
docker-compose logs scheduler
```

### DAG import errors

```bash
# Inspect DAG parsing errors in the scheduler
docker-compose logs scheduler | grep -i "error\|import"
```

### Forecast file missing (503 from FastAPI or blank dashboard)

The FastAPI service and Streamlit dashboard both depend on `data/predictions/m5_forecast.parquet`. Run the pipeline in order:

1. `m5_preprocessing_pipeline`
2. `m5_training_pipeline`
3. Call `POST /refresh` on the FastAPI service (or restart the container)

### Port conflicts

Modify the left-hand port numbers in `docker-compose.yml`:

```yaml
ports:
  - "8082:8080"   # change 8081 → 8082 for Airflow UI
  - "8001:8000"   # change 8000 → 8001 for FastAPI
  - "8502:8501"   # change 8501 → 8502 for Streamlit
```

### Rebuilding the image after dependency changes

```bash
docker-compose build --no-cache
docker-compose up -d
```

---

## Dependencies

| Package | Version | Role |
|---|---|---|
| `apache-airflow` | 3.1.0 | Pipeline orchestration |
| `statsforecast` | 1.7.8 | Statistical forecasting models |
| `lightgbm` | 4.6.0 | Gradient boosting ML model |
| `pandas` | 2.3.3 | Data manipulation |
| `numpy` | 2.3.4 | Numerical computing |
| `scikit-learn` | 1.7.2 | Evaluation utilities |
| `fastapi` | 0.120.0 | REST API framework |
| `uvicorn` | 0.38.0 | ASGI server |
| `joblib` | 1.5.2 | Model serialisation |
| `pyarrow` / `fastparquet` | latest | Parquet I/O |

See `requirements.txt` for the complete pinned list.

---

## License

MIT License

## Author

Israel Igietsemhe

---

For more information about the M5 Forecasting competition, visit:
https://www.kaggle.com/c/m5-forecasting-accuracy
