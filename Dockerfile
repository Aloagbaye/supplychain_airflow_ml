# ==============================
# Custom Airflow 3.1 build for M5 pipeline
# ==============================
FROM apache/airflow:3.1.0

USER root

# Install system dependencies (needed for pandas/pyarrow)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create data directories and set permissions
RUN mkdir -p \
    /opt/airflow/data/raw \
    /opt/airflow/data/processed \
    /opt/airflow/data/intermediate \
    /opt/airflow/data/predictions \
    /opt/airflow/data/deployed \
    /opt/airflow/models \
    /opt/airflow/outputs \
    && chown -R airflow:root /opt/airflow/data /opt/airflow/models /opt/airflow/outputs \
    && chmod -R 775 /opt/airflow/data /opt/airflow/models /opt/airflow/outputs

# Copy your M5 dataset from host into image
COPY ./data/raw /opt/airflow/data/raw

# Switch to airflow user
USER airflow

# Install Python dependencies (kept in sync with requirements.txt)
RUN pip install --no-cache-dir \
    statsforecast==1.7.8 \
    lightgbm==4.6.0 \
    pandas==2.3.3 \
    pyarrow \
    fastparquet \
    numpy==2.3.4 \
    scikit-learn==1.7.2 \
    scipy==1.16.2 \
    joblib==1.5.2

# Confirm installation
RUN python -c "import statsforecast, lightgbm, pandas, pyarrow; print('✅ Airflow build ready')"
