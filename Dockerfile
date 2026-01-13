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
RUN mkdir -p /opt/airflow/data/raw /opt/airflow/data/processed \
    && chown -R airflow:root /opt/airflow/data \
    && chmod -R 775 /opt/airflow/data

# Copy your M5 dataset from host into image
COPY ./data/raw /opt/airflow/data/raw

# Switch to airflow user
USER airflow

# Install Python dependencies
RUN pip install --no-cache-dir \
    statsforecast==1.7.7 \
    pandas==2.2.3 \
    pyarrow==17.0.0 \
    fastparquet==2024.5.0 \
    numpy==1.26.4 \
    scikit-learn==1.5.2

# Confirm installation
RUN python -c "import statsforecast, pandas, pyarrow; print('✅ Airflow build ready')"
