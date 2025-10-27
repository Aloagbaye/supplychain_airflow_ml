# 🧠 Apache Airflow Cheat Sheet

A quick reference guide for using **Apache Airflow** to orchestrate data and machine learning workflows.

---

## 🚀 What is Apache Airflow?
- **Workflow orchestration tool** for programmatically authoring, scheduling, and monitoring workflows.
- Uses **DAGs (Directed Acyclic Graphs)** to define task dependencies.
- Web UI for monitoring and manual triggering.

---

## 🕸️ DAG Basics
```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def my_task():
    print("Hello Airflow")

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
    'retries': 1
}

dag = DAG(
    dag_id='example_dag',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False
)

start = PythonOperator(
    task_id='print_hello',
    python_callable=my_task,
    dag=dag
)
```

---

## ⚙️ Core Concepts

| Concept | Description |
|--------|-------------|
| DAG | Blueprint of the workflow; defines task order and dependencies |
| Task | A single unit of work (e.g., Python function, Bash command) |
| Operator | Defines what kind of work a task does (Python, Bash, SQL, etc.) |
| TaskInstance | A specific run of a task on a given execution date |
| Schedule | Defines how often a DAG runs (e.g., `@daily`, cron format) |
| Trigger | Manually or automatically launch a DAG run |

---

## 🧩 Common Operators

```python
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# Bash
bash = BashOperator(
    task_id='bash_task',
    bash_command='echo "Hello from Bash"',
    dag=dag
)

# Python
python = PythonOperator(
    task_id='python_task',
    python_callable=lambda: print("Hello from Python"),
    dag=dag
)
```

---

## 🔄 Dependencies
```python
task1 >> task2       # task1 runs before task2
task1.set_downstream(task2)
task2.set_upstream(task1)
```

---

## 🗓️ Scheduling

| Interval | Value |
|----------|-------|
| Daily | `@daily` |
| Weekly | `@weekly` |
| Hourly | `@hourly` |
| Custom | `'0 8 * * 1'` (every Monday at 8AM) |

To **disable backfilling**, set:
```python
catchup=False
```

---

## 🔍 Monitoring
- UI: [http://localhost:8080](http://localhost:8080)
- Views: Tree View, Gantt Chart, Graph View
- Actions: Trigger DAG, pause/unpause, clear tasks

---

## 🧼 Tips
- Store scripts in `/scripts` and import them in DAGs
- Keep tasks **idempotent** (safe to run multiple times)
- Use **XComs** to pass small data between tasks
- Use `airflow.models.Variable` for configs

---

## 🐳 Docker & Dev Setup
To start Airflow using Docker Compose:
```bash
docker-compose up
```

Folder structure:
```
project/
├── dags/
├── data/
├── models/
├── scripts/
├── docker-compose.yml
```

---

## 📦 Example ML Pipeline Tasks
- `fetch_data_task`: load data from DB or CSV
- `preprocess_task`: clean & transform features
- `train_model_task`: train and store ML model
- `predict_task`: run inference
- `store_predictions_task`: save output to database

---

## 📚 Resources
- [Airflow Docs](https://airflow.apache.org/docs/)
- [Airflow Providers](https://airflow.apache.org/docs/apache-airflow-providers/)
- [Common DAG Examples](https://github.com/apache/airflow/tree/main/airflow/example_dags)

---

Happy orchestrating! ⚙️
