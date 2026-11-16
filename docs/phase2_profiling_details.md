# Phase 2: Detailed profiling results

This is the full output summary behind docs/phase2_notes.md and was produced by sql/03_profile_raw.sql.

# Phase 2 Notes: Ingestion, Raw Storage and Raw Data Profiling

Project: California Electricity Demand and Weather Analytics  
Dataset: `arimancy/caiso-hourly-demand-weather` (Kaggle, CC BY 4.0)

## 1. How the ingestion script connects to the source and handles failures

`scripts/ingest.py` is the entry point for one ingestion run. It creates a unique `batch_id`, ensures the PostgreSQL schema exists, downloads the dataset through `scripts/extract.py`, checks whether the exact file was loaded successfully before, and loads it through `scripts/load_raw.py` when it is new.

**Connecting to the source.** `scripts/extract.py` sends an HTTP GET request to the Kaggle dataset download endpoint using HTTP Basic Authentication. `KAGGLE_USERNAME`, `KAGGLE_KEY`, and the dataset slug are read from environment variables. The response is streamed in 1 MB chunks to a temporary ZIP file (connect/read timeouts: 10/300 seconds). The ZIP must contain exactly one CSV. That CSV is extracted byte-for-byte to `data/raw/caiso_hourly_<UTC timestamp>.csv`; the script then calculates its SHA-256 checksum and file size.

**Handling failures.**
- Connection errors and timeouts are retried up to `MAX_RETRIES` times. HTTP 5xx responses are also retried. The wait between attempts is exponential (`2 ** attempt` seconds).
- HTTP 401, 403, and 404 stop immediately with a specific readable error. Other non-5xx HTTP errors are not retried by the current implementation.
- A non-ZIP response, a ZIP containing other than exactly one CSV, or a CSV header that does not match the raw table columns causes the run to fail.
- The loader counts the CSV rows and compares that count with the inserted row count. A mismatch raises an error; the insert is performed in a database transaction, so a failed load is rolled back.
- `ingest.py` catches failures, logs the traceback, sets the batch status to `FAILED`, and returns exit code 1. On success it returns 0. If the file's SHA-256 already exists in a prior `SUCCESS` log entry, loading is skipped and the status is `SKIPPED`.
- A `finally` block attempts to write the run to `raw_data.ingestion_log` and prints a final summary. The log write is an attempt, not an absolute guarantee: if PostgreSQL is unavailable, the log row cannot be written; the script logs that secondary failure and returns a failure exit code.

## 2. Where and how raw data is stored

- **Raw files.** The downloaded CSV is saved under `data/raw/` on the host machine. Docker Compose bind-mounts `./data/raw` to `/data/raw` inside the ingestion container. The folder is runtime data and should not be committed to Git.
- **PostgreSQL schema `raw_data`.**
  - `raw_data.raw_caiso_hourly` stores the 35 source columns as `TEXT`, preserving the source representations without applying numeric, timestamp, or boolean conversions. Three metadata columns are added: `_batch_id` (the ingestion run), `_source_file` (the CSV filename), and `_ingested_at` (the database ingestion time).
  - `raw_data.ingestion_log` stores one record per logged run, including the batch ID, timestamps, source, HTTP status, filename, SHA-256, fetched/loaded row counts, status, and error text.
- **Loading method.** The loader creates a temporary table with the CSV source columns as `TEXT`, uses PostgreSQL `COPY` to load the CSV into it, and inserts those values into `raw_caiso_hourly` together with the batch metadata. The database operation is committed as a transaction; an exception causes rollback.
- **Append and traceability.** Each successful new-file load appends a batch; existing raw rows are not updated or deleted by this loader. The SHA-256 is a checksum/fingerprint that can be compared with a separately calculated checksum to detect a content change. A checksum value by itself does not prove that a file has never changed.
- **Profiling scope.** `sql/03_profile_raw.sql` profiles the most recently ingested batch found in the raw table. It does not profile failed or skipped attempts that added no raw rows.

## 3. Data quality issues found

The profiling SQL was run against the most recently ingested batch in PostgreSQL. The results below are from the actual query outputs, not estimates.

**Profiled batch:** `48e7a1d23f5a`  
**Source file:** `caiso_hourly_20261116T183430Z.csv`  
**Total rows:** `98,968`  
**UTC timestamp coverage:** `2015-07-01 08:00:00+00` through `2026-10-14 23:00:00+00`

### 3.1 Summary of checks

| Check / observation | Result | Interpretation / Phase 3 action |
|---|---:|---|
| Duplicate non-null `datetime_utc` groups | 0 | Checked; none found. |
| Extra rows from duplicate non-null timestamps | 0 | Checked; none found. |
| Fully identical extra rows (metadata excluded) | 0 | Checked; none found. |
| Conflicting rows sharing a UTC timestamp | 0 | Checked; none found. |
| Duplicate timestamps after parsing | 0 | Checked; none found. |
| Extra spaces at the beginning/end of source values | 0 columns affected | Checked; none found. |
| Invalid numeric representations | 0 | Checked; none found among the profiled numeric columns. |
| Non-integer values in integer-typed source columns | 0 | Checked; none found. |
| Invalid boolean spellings | 0 | Boolean values were represented as `True` / `False`; no other spelling was observed. |
| Numeric out-of-range checks in Q6a | 0 | No violations were found for the tested demand, weather, temperature, degree-day, hour, month, or day-of-week rules. The temperature range `-10..50 °C` is a screening assumption, not a source-defined limit. |
| `hour` compared with `datetime_local` | 0 mismatches | The `hour` field agrees with the local wall-clock hour. |
| `hour` compared with `datetime_utc` | 98,968 mismatches (100%) | This is a time-basis difference, not an invalid-hour result: `hour` matches `datetime_local`, not the UTC wall-clock hour. Preserve/document the source convention and use the appropriate timestamp basis in transformations. |
| Timestamp format mismatches | 0 | Both timestamp columns consistently matched the tested ISO-like pattern. |
| Values matching the timestamp pattern but failing timestamp parsing | 0 | All tested values parsed successfully. |
| Repeated full `datetime_local` values | 0 | Checked; none found. |
| Missing hourly UTC timestamps within the observed range | 0 | All expected hourly UTC timestamps were present. |
| UTC timestamps not aligned to the beginning of an hour | 0 | All valid UTC timestamps had minute and second equal to zero. |

### 3.2 Missing values

The following were the columns with missing values in the raw batch:

| Column | Missing rows | % of 98,968 rows |
|---|---:|---:|
| `demand_imputed_pudl_mwh_imputation_code` | 98,397 | 99.423% |
| `demand_imputed_pudl_mwh` | 928 | 0.938% |
| `demand_reported_mwh` | 426 | 0.430% |
| `cdd_65_daily` | 40 | 0.040% |
| `hdd_65_daily` | 40 | 0.040% |

Missing values should not automatically be treated as errors. In Phase 3, retain NULLs or apply a documented, column-specific imputation rule based on the field's meaning and downstream requirements. The imputation-code column is mostly empty, so its NULL values should not be interpreted as missing demand values by themselves.

### 3.3 Demand source and imputation metadata

`demand_source` distribution:

| Source | Rows |
|---|---:|
| `pudl` | 98,040 |
| `eia_api` | 928 |

`demand_imputed_pudl_mwh_imputation_code` distribution:

| Code | Rows |
|---|---:|
| NULL / blank | 98,397 |
| `missing_value` | 426 |
| `anomalous_region` | 103 |
| `double_delta` | 19 |
| `local_outlier_low` | 19 |
| `single_delta` | 3 |
| `identical_run` | 1 |

The code values indicate categories associated with missing or anomalous demand observations. Their exact algorithmic definitions should be taken from the dataset/source documentation rather than inferred solely from the labels. Preserve this metadata in the cleaned layer.

### 3.4 Time, calendar and daylight-saving observations

- `day_of_week` uses **0 = Monday** through **6 = Sunday**. The `is_weekend` flag is `True` for 5 (Saturday) and 6 (Sunday), and `False` for 0–4.
- All hour values from 0 to 23 and all month values from 1 to 12 were present.
- The difference `local_wall - utc_wall` had two observed offsets: `-08:00` for 33,611 rows and `-07:00` for 65,357 rows. These correspond to California standard time and daylight time respectively.
- Complete local dates flagged as DST transition days had 23 rows on 11 dates and 25 rows on 11 dates. Complete non-transition dates had 24 rows on 4,100 dates.
- Two edge dates were incomplete within the extracted dataset window: 2015-07-01 had 23 rows and 2026-10-14 had 17 rows; both were not flagged as DST transition days. These are consistent with the dataset beginning and ending partway through a local day, rather than evidence of internal hourly gaps.
- There were no duplicate full `datetime_local` values. During the fall-back transition, repeated local clock hours can still be distinct full timestamps because their UTC offsets differ.

Use UTC as the stable time key for joins, ordering and time-series continuity. Preserve the local timestamp and the DST indicator for local-calendar analysis. Do not compare the `hour` field to the UTC clock hour; the observed data shows it aligns with the local clock hour.

### 3.5 Numeric ranges and informational flags

Observed minimum and maximum values included:
- `demand_mwh` and `demand_imputed_pudl_mwh`: 14,372 to 51,104.
- `demand_reported_mwh`: 14 to 51,104.
- `cloud_cover_pop_wt_pct`: 0 to 100.
- `shortwave_radiation_pop_wt_wm2`: 0 to 1,045.372.
- `temp_pop_wt_c`: approximately 2.050 to 42.850 °C.
- City temperature columns ranged from -2.4 to 47.8 °C across the observed cities.

The minimum reported demand value (14 MWh) is much smaller than the minimum of the other demand fields. This is an observation to investigate against source definitions and the corresponding records; it was not classified as invalid by the range checks.

Informational flags:

| Flag | Value | Rows | % of rows |
|---|---|---:|---:|
| `demand_is_imputed` | `True` | 571 | 0.577% |
| `demand_is_imputed` | `False` | 98,397 | 99.423% |
| `temp_is_missing` | `True` | 0 | 0.000% |
| `temp_is_missing` | `False` | 98,968 | 100.000% |
| `temp_is_imputed` | `True` | 0 | 0.000% |
| `temp_is_imputed` | `False` | 98,968 | 100.000% |
| `weather_is_preliminary` | `True` | 1,947 | 1.967% |
| `weather_is_preliminary` | `False` | 97,021 | 98.033% |

These flags are informational metadata, not automatically data-quality failures. Preserve them so downstream analysis can filter or compare imputed demand and preliminary weather records.

### 3.6 Recommended Phase 3 handling

1. Keep the raw layer unchanged and create typed/cleaned columns in a downstream layer.
2. Parse UTC and local timestamps into appropriate timestamp types; use UTC as the stable hourly key.
3. Keep `hour` interpreted as local hour, and document the `day_of_week` convention (Monday = 0).
4. Preserve demand source, imputation codes, and all quality flags.
5. Investigate the unusually low `demand_reported_mwh` minimum and confirm the semantics of imputation codes using source documentation before deciding on any filtering or imputation.
6. Treat the `-10..50 °C` temperature check as a screening assumption only.
7. Do not fill the partial first/last local dates merely to make every date contain 24 rows; distinguish dataset boundaries from internal missing timestamps.

## 4. AI usage disclosure

ChatGPT (OpenAI) was used to assist with reviewing and editing the profiling SQL and this notes document. The author is responsible for checking the SQL against the repository schema, running the queries on the actual loaded batch, interpreting the results, and verifying every reported number against the query output. Any other AI tools used during preparation should also be named here so the disclosure remains complete and accurate.
[TEAM: before submission, list every AI tool actually used on this project; this section must be complete and honest.]
