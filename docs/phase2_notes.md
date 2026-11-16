# Phase 2 Notes: Ingestion, Raw Storage and Raw Data Profiling

## 1. How the ingestion script connects to the source and handles failures

`scripts/ingest.py` coordinates a batch by fetching the dataset through `scripts/extract.py` and loading it through `scripts/load_raw.py`.

- `extract.py` calls the Kaggle dataset download endpoint with HTTP Basic Authentication using `KAGGLE_USERNAME` and `KAGGLE_KEY`; the dataset slug is configurable through `KAGGLE_DATASET`.
- The response is streamed to a temporary ZIP file, which must contain exactly one CSV; the CSV is extracted to a timestamped file.
- Connection errors, timeouts and HTTP 5xx responses are retried with exponential backoff. HTTP 401, 403 and 404 fail immediately with readable messages.
- The loader checks the CSV header, then uses a PostgreSQL transaction to load the rows. `ingest.py` compares fetched and loaded row counts and fails if they differ.
- `ingest.py` returns exit code 1 on failure and 0 on success or skip.
- The `finally` block attempts to record each run in `raw_data.ingestion_log` and prints a summary.

## 2. Where and how raw data is stored

- The timestamped CSV is stored under `data/raw/` on the host, bind-mounted as `/data/raw` in the ingestion container.
- PostgreSQL schema `raw_data` contains `raw_caiso_hourly` for source rows and `ingestion_log` for run metadata and outcomes.
- All 35 source columns are stored as `TEXT` to preserve the original values without premature type conversion.
- Three metadata columns in `raw_caiso_hourly` are `_batch_id`, `_source_file` and `_ingested_at`.
- New files append as batches. A SHA-256 match to a prior successful load triggers the `SKIPPED` guard instead of loading duplicate rows.

## 3. Data quality issues found

- `demand_imputed_pudl_mwh_imputation_code` is missing in 98,397 rows (99.423%); preserve NULLs and do not treat them alone as missing demand.
- `demand_imputed_pudl_mwh` is missing in 928 rows (0.938%); retain NULLs or apply a documented, field-specific Phase 3 rule.
- `demand_reported_mwh` is missing in 426 rows (0.430%); retain NULLs or apply a documented, field-specific Phase 3 rule.
- `cdd_65_daily` is missing in 40 rows (0.040%); retain NULLs or apply a documented, field-specific Phase 3 rule.
- `hdd_65_daily` is missing in 40 rows (0.040%); retain NULLs or apply a documented, field-specific Phase 3 rule.
- `hour` matches local time and differs from the UTC clock hour in 98,968 rows (100%); interpret it as local time and use UTC for stable time-series keys.
- The partial edge dates 2015-07-01 and 2026-10-14 contain 23 and 17 rows; 11 DST dates have 23 rows and 11 have 25. Preserve these boundaries and DST semantics rather than padding dates.
- `demand_is_imputed` is true for 571 rows (0.577%); preserve the informational flag for downstream filtering or comparison.
- `weather_is_preliminary` is true for 1,947 rows (1.967%); preserve the flag and account for preliminary observations in analysis.
- `demand_reported_mwh` has an unusually low minimum of 14 MWh versus 14,372 MWh for the other demand fields; investigate the corresponding records and source definitions before filtering.

Checked, none found: duplicates, invalid numerics and booleans, out-of-range values, timestamp format problems and hourly gaps.

Full results: docs/phase2_profiling_details.md

## 4. AI usage disclosure

ChatGPT (OpenAI) was used to assist with reviewing and editing the profiling SQL and this notes document. The author is responsible for checking the SQL against the repository schema, running the queries on the actual loaded batch, interpreting the results, and verifying every reported number against the query output. Any other AI tools used during preparation should also be named here so the disclosure remains complete and accurate.
[TEAM: before submission, list every AI tool actually used on this project; this section must be complete and honest.]
