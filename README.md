# 📦 OrderFlow360 — E-Commerce Order Data Quality Pipeline

OrderFlow360 is a Python-based data engineering project designed to process e-commerce order transactions, validate data quality, standardize records, and separate valid records from rejected records for downstream analytics.

The project focuses on building a reliable data preparation pipeline for order fulfillment analytics.

## 🎯 Project Objectives

- Ingest order transactions and supporting customer and courier master data from CSV files.
- Profile datasets to understand their structure, missing values, and duplicate records.
- Validate transactions against business rules and master data.
- Standardize text fields, order statuses, numeric values, and date columns.
- Derive useful fields such as order value and delivery duration.
- Separate valid records from rejected records and record the reasons for rejection.
- Reconcile processed records to verify pipeline consistency.

## 🛠️ Technology Stack

- **Python** — pipeline implementation
- **Pandas** — data manipulation and transformation
- **CSV** — source and processed data storage
- **Git & GitHub** — version control

## 📁 Project Structure

```text
OrderFlow360/
├── data/
│   ├── raw/                  # Source CSV datasets (not tracked in Git)
│   ├── processed/            # Cleaned data outputs (not tracked in Git)
│   └── rejected/             # Rejected records (not tracked in Git)
├── src/
│   ├── ingestion.py          # Loads source datasets
│   ├── profiling.py          # Profiles datasets
│   ├── validation.py         # Applies data quality rules
│   ├── transformation.py     # Standardizes and derives fields
│   ├── warehouse.py          # Reserved for analytical storage integration
│   ├── analytics.py          # Reserved for analytical processing
│   └── pipeline.py           # Coordinates pipeline execution
├── sql/
│   ├── schema.sql
│   └── kpi_queries.sql
├── reports/                  # Reserved for reports
├── main.py
├── requirements.txt
├── dashboard.py              # Dashboard development
├── README.md
└── .gitignore
```

## 📥 Data Sources

The pipeline uses four source datasets:

| Dataset | Purpose |
|---|---|
| `order_transactions_v3.csv` | Order transaction records |
| `order_transactions_dirty_v3.csv` | Transactions containing data quality issues |
| `customer_master_orders_v3.csv` | Customer reference data |
| `courier_sla_master_v3.csv` | Courier details and service-level agreements (SLAs) |

The datasets are maintained locally and are excluded from the public repository.

## ⚙️ Data Pipeline Workflow

### 1. Data Ingestion

Loads the transaction datasets and supporting customer and courier master data from CSV files using Pandas. The ingestion module also checks whether the expected source files exist.

### 2. Data Profiling

Examines dataset dimensions, column names, duplicate rows, missing values, and sample records to understand the initial data quality.

### 3. Data Validation

Applies business rules to identify invalid records, including:

- Missing required identifiers
- Invalid or non-positive unit prices
- Invalid, non-positive, or non-integer quantities
- Invalid order dates
- Inconsistent order, shipment, and delivery date sequences
- Duplicate transactions
- Customer IDs not found in the customer master
- Courier names that cannot be matched to the courier master

Rejected records retain a `REJECTION_REASON` field describing the validation failures.

### 4. Data Transformation

Standardizes text fields and order statuses, converts numeric and date fields to appropriate types, normalizes recognized courier names, and derives additional fields.

**Derived fields include:**

- `ORDER_VALUE` — unit price multiplied by quantity
- `DELIVERY_DURATION_DAYS` — elapsed time between shipment and delivery when both dates are available

### 5. Valid and Rejected Record Separation

Separates records into two outputs:

- `data/processed/orders_clean.csv`
- `data/rejected/orders_rejected.csv`

The pipeline also prepares cleaned customer and courier master files for subsequent processing.

### 6. Data Quality Reconciliation

Compares the total number of input records with the number of valid and rejected records to check that every input record is accounted for.

## 📊 Pipeline Outputs

| Output file | Description |
|---|---|
| `orders_clean.csv` | Validated and transformed order records |
| `customers.csv` | Customer master data |
| `couriers.csv` | Courier reference data |
| `orders_rejected.csv` | Rejected transactions with rejection reasons |

These outputs provide the prepared datasets required for subsequent analytical processing.

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or later
- pip
- Git (optional, for cloning the repository)

### 1. Clone the repository

```bash
git clone https://github.com/manojdharavath/OrderFlow360.git
cd OrderFlow360
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Add the source datasets

Place the required CSV files in `data/raw/` using the filenames listed in the Data Sources section.

### 4. Run the pipeline

```bash
python main.py
```

If your project currently uses `src/pipeline.py` as its entry point, run:

```bash
python src/pipeline.py
```

Use the entry point that matches your current project configuration.

### 5. Check the outputs

After a successful run, inspect:

- `data/processed/`
- `data/rejected/`

Confirm that the cleaned and rejected CSV files have been generated and that the reconciliation check passes.

## 🔒 Data Privacy

Raw source data, processed datasets, rejected records, local configuration files, and other potentially sensitive data are excluded from version control through `.gitignore`.

## 🔮 Planned Enhancements

The following are future development goals, not claims of completed functionality:

- Analytical storage and KPI computation using DuckDB
- Order fulfillment and courier performance analysis
- Interactive Streamlit dashboard with charts, KPI cards, and filters
- Additional data quality reporting and operational insights

## 👨‍💻 Author

**Dharavath Manoj**
**Aryan kherwal**
**Vedant Sharma**

---

*OrderFlow360 — Preparing reliable order data for better fulfillment analytics.*
