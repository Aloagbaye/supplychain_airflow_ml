# Supply Chain ML with Apache Airflow

A production-ready machine learning pipeline for supply chain demand forecasting using the M5 Forecasting dataset. This project leverages Apache Airflow 3.1.0 to orchestrate data preprocessing, model training, and batch inference workflows, with a FastAPI service for real-time predictions and a Streamlit dashboard for monitoring.

## 🎯 Project Overview

This project implements an end-to-end ML pipeline for forecasting retail demand using the M5 (Walmart) dataset. The system processes historical sales data, trains forecasting models using StatsForecast, and provides both batch and real-time prediction capabilities.

## ✨ Features

- **Automated Data Pipeline**: Preprocesses M5 dataset and converts to Nixtla/StatsForecast format
- **ML Model Training**: Trains time series forecasting models using StatsForecast
- **Batch Inference**: Scheduled batch predictions via Airflow DAGs
- **Real-time API**: FastAPI service for on-demand predictions
- **Monitoring Dashboard**: Streamlit dashboard for visualizing predictions and metrics
- **Containerized Deployment**: Fully containerized with Docker Compose
- **Scalable Architecture**: Multi-service architecture with PostgreSQL backend

## 🏗️ Architecture

The project consists of the following services:

- **PostgreSQL**: Database backend for Airflow metadata
- **Airflow Scheduler**: Orchestrates DAG execution
- **Airflow API Server**: REST API for Airflow operations (port 8081)
- **FastAPI Service**: ML prediction service (port 8000)
- **Streamlit Dashboard**: Monitoring and visualization (port 8501)

## 📋 Prerequisites

- Docker and Docker Compose installed
- At least 8GB RAM available for containers
- M5 dataset files in `data/raw/` directory:
  - `sales_train_validation.csv`
  - `calendar.csv`
  - `sell_prices.csv` (optional)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd supplychain_airflow_ml
```

### 2. Prepare Data

Place your M5 dataset files in the `data/raw/` directory:
- `sales_train_validation.csv`
- `calendar.csv`
- `sell_prices.csv` (optional)

### 3. Build and Start Services

```bash
# Build the custom Airflow image
docker-compose build

# Start all services
docker-compose up -d
```

### 4. Access Services

- **Airflow UI**: http://localhost:8081
  - Username: `admin`
  - Password: `admin`
- **FastAPI Service**: http://localhost:8000
- **Streamlit Dashboard**: http://localhost:8501

### 5. Run the Pipeline

1. Open the Airflow UI at http://localhost:8081
2. Enable and trigger the `m5_preprocessing_pipeline` DAG
3. Once preprocessing completes, trigger `m5_training_pipeline` DAG
4. For batch inference, trigger `m5_batch_inference_dag` DAG

## 📁 Project Structure

```
supplychain_airflow_ml/
├── dags/                      # Airflow DAG definitions
│   ├── m5_preprocessing_dag.py
│   ├── m5_training_dag.py
│   └── m5_batch_inference_dag.py
├── scripts/                   # Python scripts for ML tasks
│   ├── preprocess.py          # Data preprocessing
│   ├── train_model.py         # Model training
│   ├── predict.py             # Batch prediction
│   ├── predict_service.py     # FastAPI prediction service
│   └── feature_engineering.py
├── data/                      # Data directories
│   ├── raw/                   # Raw M5 dataset files
│   ├── processed/             # Preprocessed data
│   ├── intermediate/          # Intermediate processing files
│   └── predictions/           # Model predictions
├── models/                    # Trained model artifacts
├── outputs/                   # API prediction outputs
├── plugins/                   # Airflow plugins
├── config/                    # Configuration files
├── docker-compose.yml         # Docker Compose configuration
├── Dockerfile                 # Custom Airflow image definition
└── requirements.txt           # Python dependencies
```

## 🔄 DAGs Description

### 1. `m5_preprocessing_pipeline`

Converts raw M5 dataset to Nixtla/StatsForecast format.

- **Schedule**: `@once` (manual trigger)
- **Tasks**:
  - `preprocess_m5_data`: Transforms sales data from wide format to long format with `unique_id`, `ds`, and `y` columns

### 2. `m5_training_pipeline`

Trains forecasting models and generates predictions.

- **Schedule**: `None` (manual trigger)
- **Tasks**:
  - `load_data`: Loads preprocessed data
  - `train_model`: Trains StatsForecast model (SimpleExponentialSmoothingOptimized)
  - `evaluate_model`: Evaluates model performance
  - `deploy_predictions`: Deploys predictions to production directory

### 3. `m5_batch_inference_dag`

Performs batch inference on new data.

- **Schedule**: Configurable
- Generates predictions for all items in the dataset

## 🔌 API Documentation

### FastAPI Service (Port 8000)

#### POST `/predict`

Generate predictions for a specific item.

**Request Body:**
```json
{
  "unique_id": "HOBBIES_1_001_CA_1_validation",
  "horizon": 28
}
```

**Response:**
```json
{
  "status": "ok",
  "rows": 28,
  "saved_to": "/opt/airflow/outputs/predictions_log.parquet"
}
```

**Example using curl:**
```bash
curl -X POST "http://localhost:8000/predict" \
  -H "Content-Type: application/json" \
  -d '{"unique_id": "HOBBIES_1_001_CA_1_validation", "horizon": 28}'
```

## 🛠️ Configuration

### Environment Variables

Create a `.env` file in the project root (optional, defaults are used if not provided):

```env
AIRFLOW_UID=50000
AIRFLOW_GID=0
```

### Data Sampling

To speed up development/testing, you can limit the number of items processed:

- In `scripts/preprocess.py`: Set `sample_items` parameter (default: 1000)
- In `dags/m5_training_dag.py`: Set `sample_rows` parameter (default: 200,000)

## 📦 Dependencies

Key Python packages:
- `apache-airflow==3.1.0`
- `statsforecast` - Time series forecasting
- `lightgbm` - Gradient boosting models
- `pandas==2.3.3` - Data manipulation
- `scikit-learn==1.7.2` - Machine learning utilities
- `fastapi==0.120.0` - API framework
- `pyarrow` & `fastparquet` - Parquet file support

See `requirements.txt` for the complete list.

## 🔧 Development

### Running Scripts Locally

If you want to run scripts outside of Airflow:

```bash
# Activate virtual environment (if using one)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run preprocessing
python scripts/preprocess.py
```

### Building Custom Airflow Image

The `Dockerfile` extends the official Apache Airflow 3.1.0 image with:
- System dependencies (build tools, PostgreSQL client)
- Python ML libraries (StatsForecast, pandas, scikit-learn)
- Data directory structure

To rebuild:
```bash
docker-compose build airflow-init api-server scheduler fastapi-service
```

## 📊 Data Format

### Input Format (Raw M5 Data)
- Wide format with columns: `id`, `item_id`, `dept_id`, `cat_id`, `store_id`, `state_id`, `d_1`, `d_2`, ..., `d_1913`

### Processed Format (Nixtla/StatsForecast)
- Long format with columns:
  - `unique_id`: Item identifier (e.g., "HOBBIES_1_001_CA_1_validation")
  - `ds`: Date (datetime)
  - `y`: Demand value (numeric)

## 🐛 Troubleshooting

### Airflow Services Not Starting

1. Check if PostgreSQL is healthy:
   ```bash
   docker-compose ps postgres
   ```

2. Check logs:
   ```bash
   docker-compose logs airflow-init
   docker-compose logs scheduler
   ```

### Missing Data Files

Ensure M5 dataset files are in `data/raw/` before building the Docker image, or mount the directory as a volume.

### Port Conflicts

If ports 8081, 8000, or 8501 are already in use, modify the port mappings in `docker-compose.yml`.

## 📝 Notes

- The project uses Airflow 3.1.0 with LocalExecutor
- Data persistence is handled via Docker volumes
- Model artifacts are stored in `/opt/airflow/models/`
- Predictions are logged to `/opt/airflow/outputs/`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

MIT License

## 👤 Author

Israel Igietsemhe

---

For more information about the M5 Forecasting competition, visit: https://www.kaggle.com/c/m5-forecasting-accuracy

