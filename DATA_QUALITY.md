
# Data Quality Checks

## 1. Purpose

This document describes the post-load data quality checks performed on the data warehouse.

The checks verify that the warehouse data is valid, consistent, complete, and correctly loaded from the staging tables.

The checks are implemented in `sql/quality_checks.sql` and executed by `scripts/run_quality.py`.

## 2. Quality Rules

The quality checks cover the following categories:

### Primary Key Uniqueness

Checks that primary key values are not duplicated in warehouse dimension and fact tables.

### Foreign Key Integrity

Checks that foreign key values reference existing records in the corresponding dimension tables.

### NULL Percentage Thresholds

Checks that the percentage of missing values does not exceed the allowed thresholds.

| Column | Maximum NULL Percentage |
|---|---:|
| demand_reported_mwh | 1.0% |
| demand_imputed_pudl_mwh | 2.0% |
| hdd_65_daily | 0.1% |
| cdd_65_daily | 0.1% |

### Value Range Validation

Checks that warehouse values remain within valid ranges.

Examples include:
- Demand values must not be negative or zero.
- Cloud cover must be between 0 and 100.
- Weather measurements must not be negative.
- Month, hour, and weekday values must be valid.

### Row Count Validation

Compares staging row counts with their corresponding warehouse tables to identify missing or additional records.

The city temperature fact table is expected to contain seven city records per staging row.

## 3. Execution

Run the post-load quality checks using:

```powershell
python scripts/run_quality.py
```

The script connects to PostgreSQL, executes the SQL checks, logs the result of each check, and fails if any check violates its threshold.

## 4. Failure Behavior

Each check produces either PASS or FAIL.

- PASS: The observed value is within the allowed threshold.
- FAIL: The observed value exceeds the allowed threshold.

If one or more checks fail, the runner raises `DataQualityError` and exits with status code 1.

If all checks pass, the runner exits with status code 0.

## 5. Failure Demonstration

The failure demonstration is implemented in:

`scripts/demo_quality_fail.py`

It creates a separate, unconstrained PostgreSQL schema named `dw_test`.

The script inserts deliberately invalid records to demonstrate that the checks can detect issues such as:

- Duplicate primary keys.
- Broken foreign key references.
- Excessive NULL percentages.
- Invalid numerical values.
- Invalid date and time values.
- Duplicate fact records.

The demo excludes staging-to-warehouse row count checks because it uses independent test data rather than the real staging tables.

After the demonstration, the `dw_test` schema is dropped.

Run the demonstration using:

```powershell
python scripts/demo_quality_fail.py
```

## 6. Example Logs

The following logs illustrate the expected output format. They are examples, not results from an actual database execution.

```text
2026-11-23T12:00:00+00:00 | INFO | run_quality | PASS | dim_city_pk | observed=0 | threshold=0
2026-11-23T12:00:00+00:00 | ERROR | run_quality | FAIL | fact_demand_pk | observed=2 | threshold=0
2026-11-23T12:00:00+00:00 | ERROR | run_quality | FAIL | demand_reported_null_pct | observed=100.0 | threshold=1.0
2026-11-23T12:00:00+00:00 | ERROR | run_quality | DATA QUALITY FAILURE: 2 of 25 post-load quality checks failed
```

## 7. Implementation Files

| File | Responsibility |
|---|---|
| `scripts/dq_common.py` | Shared data quality classes |
| `scripts/logging_config.py` | Standard logging configuration |
| `sql/quality_checks.sql` | SQL quality rules |
| `scripts/run_quality.py` | Executes post-load checks |
| `scripts/demo_quality_fail.py` | Demonstrates intentional failures |
