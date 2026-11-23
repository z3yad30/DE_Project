# Data Quality

## Purpose and execution

Quality gates run before and after the warehouse load:

1. Python pre-load checks validate the typed clean batch against the selected
   raw batch. Any failed result raises `DataQualityError`.
2. SQL post-load checks validate `dw`, the clean staging count, and the latest
   successful raw batch. `run_quality(connection, schema="dw")` uses the caller's
   open connection and does not commit, roll back, or close it.

Run the standalone post-load checker with:

```sh
python scripts/run_quality.py
```

Run a failure demonstration against an isolated copy of the warehouse with:

```sh
python scripts/demo_quality_fail.py --case duplicate_pk
python scripts/demo_quality_fail.py --case negative_demand
python scripts/demo_quality_fail.py --case orphan_fk
python scripts/demo_quality_fail.py --case null_spike
```

## Rules

The Python checks and SQL checks are separate tiers; together they enforce the
following rules. A failed result logs its check name and observed failure count.

| Rule | Description | Tier | Threshold | Failure behavior |
|---|---|---|---|---|
| `required_columns` | All declared clean-staging columns are present. | Python pre-load | 0 missing columns | Reject the batch. |
| `expected_dtypes` | Clean columns match their declared datetime, numeric, integer, boolean, and text types. | Python pre-load | 0 mismatches | Reject the batch. |
| `row_count` | Clean rows equal selected raw-batch rows minus documented removals. | Python pre-load | 0 removals; 0 row difference | Reject the batch. |
| `datetime_utc_not_null` | UTC timestamp key is present. | Python pre-load | 0 NULLs | Reject the batch. |
| `datetime_utc_unique` | UTC timestamp key is unique. | Python pre-load | 0 duplicate rows | Reject the batch. |
| `demand_mwh_positive` | Demand is present and positive. | Python pre-load | 0 NULL or non-positive values | Reject the batch. |
| `demand_reported_mwh_null_share` | Reported demand missing-value share. | Python pre-load | At most 1% | Reject if the percentage exceeds the limit. |
| `demand_imputed_pudl_mwh_null_share` | Imputed PUDL demand missing-value share. | Python pre-load | At most 2% | Reject if the percentage exceeds the limit. |
| `hdd_65_daily_null_share` | Daily heating-degree missing-value share. | Python pre-load | At most 0.1% | Reject if the percentage exceeds the limit. |
| `cdd_65_daily_null_share` | Daily cooling-degree missing-value share. | Python pre-load | At most 0.1% | Reject if the percentage exceeds the limit. |
| `cloud_cover_pop_wt_pct_range` | Population-weighted cloud cover. | Python pre-load | 0–100 inclusive | Reject out-of-range values. |
| `shortwave_radiation_pop_wt_wm2_range` | Population-weighted shortwave radiation. | Python pre-load | At least 0 | Reject negative values. |
| `hdh_65_range` | Hourly heating-degree hours. | Python pre-load | At least 0 | Reject negative values. |
| `cdh_65_range` | Hourly cooling-degree hours. | Python pre-load | At least 0 | Reject negative values. |
| `hdd_65_daily_range` | Daily heating-degree days. | Python pre-load | At least 0 | Reject negative values. |
| `cdd_65_daily_range` | Daily cooling-degree days. | Python pre-load | At least 0 | Reject negative values. |
| `hour_range` | Local hour value. | Python pre-load | 0–23 inclusive | Reject out-of-range values. |
| `month_range` | Local month value. | Python pre-load | 1–12 inclusive | Reject out-of-range values. |
| `day_of_week_range` | Weekday value, Monday = 0. | Python pre-load | 0–6 inclusive | Reject out-of-range values. |
| `dim_holiday_pk` | Holiday dimension primary-key uniqueness. | SQL post-load | 0 duplicate keys | Raise `DataQualityError`. |
| `dim_datetime_pk` | Datetime dimension primary-key uniqueness. | SQL post-load | 0 duplicate keys | Raise `DataQualityError`. |
| `datetime_utc_not_null` | Datetime dimension UTC key is present. | SQL post-load | 0 NULLs | Raise `DataQualityError`. |
| `datetime_utc_unique` | Datetime dimension UTC key is unique. | SQL post-load | 0 duplicate rows | Raise `DataQualityError`. |
| `dim_city_pk` | City dimension primary-key uniqueness. | SQL post-load | 0 duplicate keys | Raise `DataQualityError`. |
| `fact_demand_pk` | Demand fact primary-key uniqueness. | SQL post-load | 0 duplicate keys | Raise `DataQualityError`. |
| `fact_weather_weighted_pk` | Weighted-weather fact primary-key uniqueness. | SQL post-load | 0 duplicate keys | Raise `DataQualityError`. |
| `fact_city_temperature_pk` | City-temperature composite primary-key uniqueness. | SQL post-load | 0 duplicate keys | Raise `DataQualityError`. |
| `datetime_holiday_fk` | Every datetime holiday reference has a dimension row. | SQL post-load | 0 orphan rows | Raise `DataQualityError`. |
| `demand_datetime_fk` | Every demand datetime reference has a dimension row. | SQL post-load | 0 orphan rows | Raise `DataQualityError`. |
| `weather_datetime_fk` | Every weather datetime reference has a dimension row. | SQL post-load | 0 orphan rows | Raise `DataQualityError`. |
| `city_temperature_datetime_fk` | Every city-temperature datetime reference has a dimension row. | SQL post-load | 0 orphan rows | Raise `DataQualityError`. |
| `city_temperature_city_fk` | Every city-temperature city reference has a dimension row. | SQL post-load | 0 orphan rows | Raise `DataQualityError`. |
| `demand_reported_null_pct` | Reported demand missing-value share. | SQL post-load | At most 1% | Fail when percentage exceeds the limit. |
| `demand_imputed_null_pct` | Imputed PUDL demand missing-value share. | SQL post-load | At most 2% | Fail when percentage exceeds the limit. |
| `hdd_daily_null_pct` | Daily heating-degree missing-value share. | SQL post-load | At most 0.1% | Fail when percentage exceeds the limit. |
| `cdd_daily_null_pct` | Daily cooling-degree missing-value share. | SQL post-load | At most 0.1% | Fail when percentage exceeds the limit. |
| `demand_mwh_positive` | Demand is present and positive. | SQL post-load | 0 NULL or non-positive values | Raise `DataQualityError`. |
| `cloud_cover_range` | Population-weighted cloud cover. | SQL post-load | 0–100 inclusive | Raise `DataQualityError` for out-of-range values. |
| `shortwave_radiation_non_negative` | Population-weighted shortwave radiation. | SQL post-load | At least 0 | Raise `DataQualityError` for negative values. |
| `hdh_65_non_negative` | Hourly heating-degree hours. | SQL post-load | At least 0 | Raise `DataQualityError` for negative values. |
| `cdh_65_non_negative` | Hourly cooling-degree hours. | SQL post-load | At least 0 | Raise `DataQualityError` for negative values. |
| `hdd_65_daily_non_negative` | Daily heating-degree days. | SQL post-load | At least 0 | Raise `DataQualityError` for negative values. |
| `cdd_65_daily_non_negative` | Daily cooling-degree days. | SQL post-load | At least 0 | Raise `DataQualityError` for negative values. |
| `datetime_month_range` | Datetime month value. | SQL post-load | 1–12 inclusive | Raise `DataQualityError` for out-of-range values. |
| `datetime_hour_range` | Local hour value. | SQL post-load | 0–23 inclusive | Raise `DataQualityError` for out-of-range values. |
| `datetime_day_of_week_range` | Weekday value, Monday = 0. | SQL post-load | 0–6 inclusive | Raise `DataQualityError` for out-of-range values. |
| `latest_success_batch_exists` | A latest successful raw batch is available for comparison. | SQL post-load | 1 selected SUCCESS batch | Raise `DataQualityError` if none exists. |
| `raw_batch_vs_clean` | Latest successful raw-batch rows equal clean-staging rows. | SQL post-load | 0 row difference | Raise `DataQualityError`. |
| `raw_batch_vs_dim_datetime` | Latest successful raw-batch rows equal datetime dimension rows. | SQL post-load | 0 row difference | Raise `DataQualityError`. |
| `raw_batch_vs_fact_demand` | Latest successful raw-batch rows equal demand fact rows. | SQL post-load | 0 row difference | Raise `DataQualityError`. |
| `raw_batch_vs_fact_weather_weighted` | Latest successful raw-batch rows equal weighted-weather fact rows. | SQL post-load | 0 row difference | Raise `DataQualityError`. |
| `dim_city_count` | Warehouse contains the seven modeled cities. | SQL post-load | Exactly 7 rows | Raise `DataQualityError`. |
| `fact_city_temperature_vs_clean` | Long city-temperature fact has seven rows per clean row. | SQL post-load | 7 × clean row count | Raise `DataQualityError` for any count difference. |

The raw batch for post-load count checks is selected from
`raw_data.ingestion_log` by `status = 'SUCCESS'`, requiring at least one
matching row in `raw_data.raw_caiso_hourly`, then ordered by completion time,
start time, and batch ID. Empty successful log entries cannot be a cleaning
source batch or satisfy the raw-to-clean checks.

## Failure and transaction policy

Each SQL row has `(check_name, failed_rows, detail)`; zero failed rows passes.
Python and SQL results use the shared `DQ PASS [name]` /
`DQ FAIL [name]: <message>` log format. The runner reports every failed check,
its count, and a summary, then raises `DataQualityError`.

The transaction boundary belongs to the pipeline caller: it opens one
transaction for batch selection, cleaning/load work, and post-load checks.
`run_quality` uses that existing connection and never commits or closes it.
If any check fails, the caller must stop later stages and roll back the
transaction so failed warehouse data is not retained.

## Failure demonstration

`scripts/demo_quality_fail.py` copies the six `dw` tables into `dw_test` with
`CREATE TABLE ... AS TABLE ... WITH NO DATA`, then copies the rows. This creates
the same columns and types but **does not copy constraints**, allowing the
demo to inject duplicate keys and orphan references. It applies one selected
corruption, runs the same SQL checks against `dw_test`, and drops `dw_test`
afterward, including on failure. The real `dw` tables are read-only inputs to
the demo.

## Evidence

Console evidence is stored in `docs/evidence/quality_pass.txt` and
`docs/evidence/quality_fail_<case>.txt`. These files contain captured run output,
not fabricated examples. The captured run used an isolated two-row test
warehouse, not the project's 98,968-row CAISO batch; it verifies the SQL and
runner behavior, not the real batch's quality.

Real excerpts from those runs:

```text
2026-11-23T16:01:01.277609+00:00 | INFO | run_quality | DQ PASS [dim_city_count]
2026-11-23T16:01:01.277857+00:00 | INFO | run_quality | DQ SUMMARY [post-load]: 34 passed, 0 failed
2026-11-23T16:01:28.153062+00:00 | ERROR | run_quality | DQ FAIL [demand_mwh_positive]: NULL or non-positive demand rows=1
2026-11-23T16:01:28.153333+00:00 | INFO | run_quality | DQ SUMMARY [post-load]: 33 passed, 1 failed
```

The clean command exited 0. Each failure command exited 1 and reported the
injected check failure; captured output for all four cases is in the evidence
files.
