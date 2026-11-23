# Project Guide

## Purpose and status

This repository builds an analytics pipeline for California electricity
demand and population-weighted weather. It downloads the CAISO hourly dataset
from Kaggle, keeps the original CSV and raw database layer, cleans a selected
batch into typed staging data, loads a PostgreSQL star schema, validates the
result, and exposes SQL views for the project's three analytical questions.

The pipeline uses Docker Compose, PostgreSQL, Python, pandas, psycopg2, and
SQL. `ingest` and `clean` are one-off Compose services; PostgreSQL and pgAdmin
are the default long-running services. Phase 3 code and documentation are in
place and were verified against the existing 98,968-row raw batch on
2026-11-23. The cleaning pipeline, warehouse, six analytical views, both
quality tiers, and intentional failure demos passed their expected outcomes.
No new Kaggle download was performed during that verification. See
[`docs/phase3_notes.md`](docs/phase3_notes.md) and the
[`Phase 3 demo checklist`](docs/lab_demo_checklist_phase3.md) for details.

## Architecture at a glance

```text
Kaggle dataset
    |
    v
scripts/extract.py -- download ZIP, extract unchanged CSV, hash it
    |
    v
data/raw/caiso_hourly_<UTC timestamp>.csv
    |
    v
scripts/ingest.py --> scripts/load_raw.py --> raw_data schema
                                               |-- raw_caiso_hourly (TEXT source values)
                                               `-- ingestion_log (batch/run metadata)
    |
    v
scripts/run_pipeline.py
    |-- scripts/clean.py --> clean_data.stg_caiso_clean
    |-- scripts/preload_checks.py
    |-- sql/04_schema_dw.sql + sql/05_load_dw.sql --> dw star schema
    `-- scripts/run_quality.py --> sql/quality_checks.sql
             |
             `-- commit only if every stage passes; otherwise rollback
    |
    v
sql/06_views_q1.sql + sql/07_views_q2.sql + sql/08_views_q3.sql
```

The raw layer is append-only from the normal ingestion path. Cleaning selects
the latest successful batch that contains raw rows, does not mutate the raw
table, and rebuilds clean staging and the warehouse in a single transaction.
Ingestion's SHA-256 duplicate-file skip and cleaning's full refresh are
different behaviors.

## Compose services

| Service | Role | Lifecycle and connections |
|---|---|---|
| `postgres` | PostgreSQL 16 database for raw, clean, and warehouse schemas. | Starts with `docker compose up -d`, persists database files in the `pgdata` named volume, exposes host port 5432, and has a `pg_isready` health check. |
| `pgadmin` | Browser-based database administration interface. | Starts after PostgreSQL is healthy, exposes host port 8080, and persists state in `pgadmin_data`. Connect to the database using host `postgres` from inside the Compose network. |
| `ingest` | Downloads the configured Kaggle dataset and loads a new CSV batch. | Profiled one-off job; run with `docker compose run --rm ingest`. It uses `.env`, connects to PostgreSQL by service name, and bind-mounts host `data/raw/` to `/data/raw`. |
| `clean` | Runs cleaning, pre-load checks, staging and warehouse loads, then post-load checks. | Profiled one-off job; run with `docker compose run --rm --build clean` initially or `docker compose run --rm clean` after building. It uses the same Dockerfile and reaches PostgreSQL at `postgres:5432`. |

`docker compose up -d` starts only the database and pgAdmin. Both pipeline
services are intentionally profiled and are not continuously running.
`scripts/Dockerfile` defaults to ingestion for the `ingest` service;
`docker-compose.yml` overrides the `clean` service command to run
`scripts/run_pipeline.py`.

## Service flows

### Ingestion: source to raw

1. `scripts/ingest.py` generates a batch ID and start timestamp, then calls
   `load_raw.ensure_schema()` to execute `sql/01_raw_schema.sql`.
2. `scripts/extract.py:fetch_source()` reads Kaggle settings from the
   environment, downloads a ZIP with retries for transient connection,
   timeout, and server failures, requires exactly one CSV, and writes the
   extracted source file unchanged to the configured raw directory. It returns
   the HTTP status, SHA-256 digest, and file size.
3. `ingest.py` counts data rows (excluding the CSV header). It calls
   `load_raw.already_loaded()` to skip a digest that already has a successful
   ingestion-log record.
4. For a new file, `load_raw.load_csv()` checks that the CSV header exactly
   matches the raw table's source columns. It stages the CSV through a
   PostgreSQL temporary table using `COPY`, then appends the values as `TEXT`
   to `raw_data.raw_caiso_hourly`, adding `_batch_id` and `_source_file`.
5. Ingestion compares fetched and inserted row counts. It records
   `SUCCESS`, `SKIPPED`, or `FAILED` plus available metadata in
   `raw_data.ingestion_log`, and prints a summary. Failed attempts return a
   nonzero exit code.

**Flow files:** `docker-compose.yml` -> `scripts/ingest.py` ->
`scripts/extract.py` -> `data/raw/*.csv` -> `scripts/load_raw.py` ->
`sql/01_raw_schema.sql` / `raw_data.*`.

### Cleaning and warehouse load: raw to analytics

1. `scripts/run_pipeline.py` opens one PostgreSQL connection. It calls
   `clean.clean_batch()` to choose the most recent `SUCCESS` batch with raw
   rows and read only that batch.
2. `clean.clean_dataframe()` trims text, turns empty strings into missing
   values, parses timestamps/numbers/integers/booleans, and checks local-time
   consistency. `clean.handle_duplicates()` removes exact duplicates and
   rejects conflicting rows at a UTC timestamp. Existing NULLs are preserved;
   they are subject to documented thresholds rather than invented
   replacement values.
3. `preload_checks.run_preload_checks()` checks required staging columns and
   dtypes, raw-to-clean row counts, timestamp key validity, demand validity,
   null shares, and field ranges. A failure prevents staging and warehouse
   writes.
4. `clean.load_staging()` fully replaces `clean_data.stg_caiso_clean` with the
   typed batch. It leaves commit/rollback to the pipeline caller.
5. The runner executes `sql/04_schema_dw.sql` and `sql/05_load_dw.sql`.
   The latter truncates and deterministically rebuilds the dimensions before
   inserting their facts.
6. `run_quality.run_quality()` executes `sql/quality_checks.sql`. If a
   post-load check fails, the runner logs the stage and error, rolls back the
   transaction, and returns exit code 1. It commits only after every check
   passes.

**Flow files:** `docker-compose.yml` -> `scripts/run_pipeline.py` ->
`scripts/clean.py` -> `scripts/preload_checks.py` -> staging ->
`sql/04_schema_dw.sql` -> `sql/05_load_dw.sql` ->
`scripts/run_quality.py` -> `sql/quality_checks.sql`.

### Analysis flow: warehouse to project questions

The three view scripts are applied after the warehouse pipeline succeeds.
They create six views in schema `dw`:

| Question | SQL file and views | Main join/grain |
|---|---|---|
| Q1: demand by temperature and the temperature interval where demand rises. | `sql/06_views_q1.sql`: `dw.v_q1_demand_by_temp_bin`, `dw.v_q1_demand_slope`. | Demand and weighted weather join by `datetime_id`; measurements are hourly. Temperature is grouped into 2°C bins. |
| Q2: seasonal daily load shape, solar/cloud measures, and midday dip. | `sql/07_views_q2.sql`: `dw.v_q2_load_shape_by_year_season_hour`, `dw.v_q2_midday_dip`. | Demand and weighted weather join by `datetime_id`; `dim_datetime` supplies local hour, year, and meteorological season. |
| Q3: calendar peak demand and which city temperature correlates most with demand. | `sql/08_views_q3.sql`: `dw.v_q3_peak_by_hour_weekend_holiday`, `dw.v_q3_city_temp_demand_corr`. | Demand joins to datetime and holiday dimensions for calendar grouping; city temperatures join to city names and demand by the shared datetime key. |

The definitions, exact JOIN justifications, and sample results are in
[`docs/phase3_notes.md`](docs/phase3_notes.md). The entity relationships are
described in [`docs/er_diagram.md`](docs/er_diagram.md), with a rendered image
at [`docs/er_diagram.png`](docs/er_diagram.png).

## Data schemas and grain

| PostgreSQL schema/table | Purpose and row grain |
|---|---|
| `raw_data.raw_caiso_hourly` | Original 35 source columns stored as `TEXT`, plus batch, file, and ingestion metadata; one row per source CSV record per loaded batch. |
| `raw_data.ingestion_log` | One row per recorded ingestion attempt, including status, row counts, file digest, and error detail. |
| `clean_data.stg_caiso_clean` | Typed, full-refresh staging; one row per UTC hour, keyed by `datetime_utc`. |
| `dw.dim_datetime` | One row per unique UTC hour; local date/time attributes, season, calendar flags, and a holiday reference. |
| `dw.dim_holiday` | One row per distinct combination of the four source holiday flags. |
| `dw.dim_city` | Seven modeled cities, one row per city. |
| `dw.fact_demand` | One row per datetime with demand and demand provenance fields. |
| `dw.fact_weather_weighted` | One row per datetime with population-weighted weather and degree-hour/day measures. |
| `dw.fact_city_temperature` | One row per datetime and city; seven records per clean hour. |

Primary keys, foreign keys, uniqueness, checks, indexes, season semantics, and
refresh order are defined in `sql/04_schema_dw.sql` and `sql/05_load_dw.sql`.
The assignment scope and validation boundaries are summarized in
[`docs/phase3_notes.md`](docs/phase3_notes.md).

## Quality and failure behavior

The Python pre-load tier is implemented in `scripts/preload_checks.py`; the
SQL post-load tier is `sql/quality_checks.sql`, executed through
`scripts/run_quality.py`. Results share `CheckResult`, `DataQualityError`, and
`log_results()` from `scripts/dq_common.py`. Full rule names, thresholds,
failure behavior, and transaction policy are in [`DATA_QUALITY.md`](DATA_QUALITY.md).

The pass demo is captured in [`docs/evidence/quality_pass.txt`](docs/evidence/quality_pass.txt).
The post-load negative-value, duplicate-key, orphan-FK, and null-spike cases
are captured in the four `docs/evidence/quality_fail_*.txt` files and run via
`scripts/demo_quality_fail.py`. `scripts/demo_preload_fail.py` demonstrates
pre-load rejection using only an in-memory copy. See the Phase 3 checklist for
the exact commands and expected behavior. Captured quality evidence uses an
isolated small fixture; do not describe it as a captured full-dataset run.

## Getting started

Requirements: Docker with Compose v2, Git, and Kaggle credentials only when
downloading a new dataset. Keep credentials in the local, ignored `.env`.
`data/raw/` is runtime output and is not committed.

```sh
cp .env.example .env
# Set the local database and Kaggle values in .env; never commit that file.
docker compose up -d
docker compose ps
docker compose run --rm ingest
docker compose run --rm --build clean
```

If a successful raw batch is already present in the database, skip ingestion
and run only the clean service. Apply the analytical views after the clean
pipeline passes:

```sh
set -a
. ./.env
set +a
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" < sql/06_views_q1.sql
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" < sql/07_views_q2.sql
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" < sql/08_views_q3.sql
```

Use the [README command reference](README.md#command-reference) and
[`docs/lab_demo_checklist_phase3.md`](docs/lab_demo_checklist_phase3.md) for
more queries, demonstrations, and troubleshooting. `docker compose down -v`
deletes named database volumes; use it only when their data may be discarded.

## File-by-file inventory

The inventory below covers maintained repository files. Runtime files and
generated files observed in the working directory are listed separately to
make clear what is not source-controlled.

### Repository root

| File | Role |
|---|---|
| [`README.md`](README.md) | Project introduction, setup and command reference, ingestion details, troubleshooting, and project roadmap. |
| [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md) | This guide: architecture, service-to-file flows, schema overview, operating steps, and file inventory. |
| [`DATA_QUALITY.md`](DATA_QUALITY.md) | Complete Python/SQL quality rule catalog, thresholds, failure behavior, transaction ownership, and evidence notes. |
| [`docker-compose.yml`](docker-compose.yml) | Defines PostgreSQL, pgAdmin, ingestion, and cleaning services, their environment, ports, volumes, health dependency, profiles, and network. |
| [`.env.example`](.env.example) | Safe template for database/pgAdmin settings and Kaggle configuration. Copy to local `.env`; keep credentials private. |
| [`.dockerignore`](.dockerignore) | Excludes Git data, credentials, runtime data, docs, and unrelated folders from Docker build context. |
| [`.gitignore`](.gitignore) | Excludes credentials, data, logs, Python caches, local environments, and database files from Git. |
| [`.gitattributes`](.gitattributes) | Requests LF-normalized text and treats PNG/PDF assets as binary. |

### `scripts/`

| File | Role and main contents |
|---|---|
| [`scripts/Dockerfile`](scripts/Dockerfile) | Builds the Python 3.11 image, installs pinned requirements, copies scripts and SQL, and defaults the container command to ingestion. |
| [`scripts/requirements.txt`](scripts/requirements.txt) | Pins `requests`, `psycopg2-binary`, and `pandas`. |
| [`scripts/extract.py`](scripts/extract.py) | `SourceResult` and `fetch_source()`: authenticate to Kaggle, retry transient download errors, extract exactly one CSV, save it unchanged, and calculate checksum/size metadata. |
| [`scripts/ingest.py`](scripts/ingest.py) | `main()`, `count_csv_rows()`, and `get_http_status()`: orchestrates schema setup, extraction, deduplication by SHA-256, row-count comparison, run logging, and exit status. |
| [`scripts/load_raw.py`](scripts/load_raw.py) | `connect()`, `ensure_schema()`, `already_loaded()`, `load_csv()`, and `record_run()`: PostgreSQL access, schema initialization, header validation, `COPY` loading, digest lookup, and ingestion logging. |
| [`scripts/clean.py`](scripts/clean.py) | `CleanStats`, `select_source_batch()`, `read_raw_batch()`, `clean_dataframe()`, `handle_duplicates()`, `clean_batch()`, `load_staging()`, and `log_stats()`: typed transformation, duplicate policy, stats, and full staging refresh. |
| [`scripts/run_pipeline.py`](scripts/run_pipeline.py) | `run_pipeline()`, `execute_sql_file()`, and `get_dw_counts()`: end-to-end transaction coordinator for cleaning, both quality tiers, DDL, warehouse load, rollback/commit, and final summary. |
| [`scripts/preload_checks.py`](scripts/preload_checks.py) | Declared clean-stage columns and dtypes, thresholds, and `run_preload_checks()` for schema, count, timestamp, missingness, demand, and range validation. |
| [`scripts/run_quality.py`](scripts/run_quality.py) | `run_quality()` executes parameterized post-load SQL on a caller-owned connection; `main()` supports standalone checking. |
| [`scripts/dq_common.py`](scripts/dq_common.py) | `CheckResult`, `DataQualityError`, and `log_results()` shared by validation code and demos. |
| [`scripts/demo_preload_fail.py`](scripts/demo_preload_fail.py) | Injects a selected defect into a copied in-memory clean DataFrame and confirms pre-load checks reject it without a database write. |
| [`scripts/demo_quality_fail.py`](scripts/demo_quality_fail.py) | Copies warehouse tables to `dw_test`, injects a duplicate key, negative demand, orphan city reference, or null spike, runs the normal SQL checks, and removes the test schema. |
| [`scripts/logging_config.py`](scripts/logging_config.py) | `UTCFormatter`, `add_stdout_handler()`, and `get_logger()` configure shared UTC-formatted stdout logging. |
| `scripts/.gitkeep` | Empty placeholder to retain the scripts directory in Git; no runtime behavior. |

### `sql/`

| File | Role |
|---|---|
| [`sql/01_raw_schema.sql`](sql/01_raw_schema.sql) | Creates `raw_data.raw_caiso_hourly`, its batch index, and `raw_data.ingestion_log`. |
| [`sql/02_raw_proof.sql`](sql/02_raw_proof.sql) | Read-only proof queries for row totals, sample rows, batch counts, recent ingestion attempts, and column types. |
| [`sql/03_profile_raw.sql`](sql/03_profile_raw.sql) | Profiles the latest raw batch for missing values, duplicates, parseability, time/calendar conventions, ranges, and flags. |
| [`sql/04_schema_dw.sql`](sql/04_schema_dw.sql) | Creates the `dw` dimensions and facts with PK/FK/unique/check constraints and query-supporting indexes. |
| [`sql/05_load_dw.sql`](sql/05_load_dw.sql) | Truncates and reloads the warehouse from clean staging; transaction control stays with the caller. |
| [`sql/06_views_q1.sql`](sql/06_views_q1.sql) | Creates Q1 temperature-bin and demand-slope views. |
| [`sql/07_views_q2.sql`](sql/07_views_q2.sql) | Creates Q2 seasonal hourly load-shape and midday-dip views. |
| [`sql/08_views_q3.sql`](sql/08_views_q3.sql) | Creates Q3 calendar peak and city-temperature correlation/ranking views. |
| [`sql/quality_checks.sql`](sql/quality_checks.sql) | Returns named post-load checks, failed-row counts, and details for the schema selected by `scripts/run_quality.py`. |
| `sql/.gitkeep` | Empty placeholder to retain the SQL directory in Git; no runtime behavior. |

### `docs/`

| File | Role |
|---|---|
| [`docs/Project_Proposal_CAISO_Demand_Weather.pdf`](docs/Project_Proposal_CAISO_Demand_Weather.pdf) | Static project proposal; read with a PDF viewer, not executed by the pipeline. |
| [`docs/architecture_phase2.png`](docs/architecture_phase2.png) | Static Phase 2 architecture diagram embedded in the README. |
| [`docs/er_diagram.md`](docs/er_diagram.md) | Mermaid description of the warehouse entities and relationships. |
| [`docs/er_diagram.png`](docs/er_diagram.png) | Rendered entity relationship diagram. |
| [`docs/phase2_notes.md`](docs/phase2_notes.md) | Ingestion, raw storage, and profiling findings summary. |
| [`docs/phase2_profiling_details.md`](docs/phase2_profiling_details.md) | Detailed outputs and interpretation for `sql/03_profile_raw.sql`. |
| [`docs/phase3_notes.md`](docs/phase3_notes.md) | Phase 3 requirement coverage, data-cleaning decisions and counts, warehouse rationale, analytical JOIN justifications, and sample results. |
| [`docs/lab_demo_checklist.md`](docs/lab_demo_checklist.md) | Earlier ingestion-focused live demonstration steps and questions. |
| [`docs/lab_demo_checklist_phase3.md`](docs/lab_demo_checklist_phase3.md) | Phase 3 pipeline, QA, warehouse inspection, analytical-view, and failure-demo runbook. |
| [`docs/.gitkeep`](docs/.gitkeep) | Empty placeholder to retain `docs/` in Git. |
| [`docs/evidence/quality_pass.txt`](docs/evidence/quality_pass.txt) | Captured post-load pass-run output on an isolated test warehouse. |
| [`docs/evidence/quality_fail_duplicate_pk.txt`](docs/evidence/quality_fail_duplicate_pk.txt) | Captured duplicate-primary-key failure output from the isolated quality demo. |
| [`docs/evidence/quality_fail_negative_demand.txt`](docs/evidence/quality_fail_negative_demand.txt) | Captured negative-demand failure output from the isolated quality demo. |
| [`docs/evidence/quality_fail_orphan_fk.txt`](docs/evidence/quality_fail_orphan_fk.txt) | Captured orphan-foreign-key failure output from the isolated quality demo. |
| [`docs/evidence/quality_fail_null_spike.txt`](docs/evidence/quality_fail_null_spike.txt) | Captured null-threshold failure output from the isolated quality demo. |

### `flows/`

| File | Role |
|---|---|
| `flows/.gitkeep` | Empty placeholder; no Kestra or other orchestration flow is implemented in this directory. |

### Runtime and ignored files observed in the current working tree

These are not maintained source files and are excluded from Git. The CSV names
are timestamp-specific downloaded inputs; future runs may create more files.

| Current file(s) | Role |
|---|---|
| `data/raw/caiso_hourly_20261116T124946Z.csv`, `data/raw/caiso_hourly_20261116T194242Z.csv`, `data/raw/caiso_hourly_20261116T194442Z.csv`, `data/raw/caiso_hourly_20261116T222245Z.csv`, `data/raw/caiso_hourly_20261116T224003Z.csv`, `data/raw/caiso_hourly_20261122T132933Z.csv` | Local source CSV snapshots produced by ingestion. They preserve the source file contents and are not tracked. |
| `.env` | Local Compose and Kaggle settings. It is ignored and may contain secrets; never commit it or publish its values. |
| `scripts/__pycache__/clean.cpython-314.pyc`, `scripts/__pycache__/demo_preload_fail.cpython-314.pyc`, `scripts/__pycache__/demo_quality_fail.cpython-314.pyc`, `scripts/__pycache__/dq_common.cpython-314.pyc`, `scripts/__pycache__/extract.cpython-314.pyc`, `scripts/__pycache__/ingest.cpython-314.pyc`, `scripts/__pycache__/load_raw.cpython-314.pyc`, `scripts/__pycache__/logging_config.cpython-314.pyc`, `scripts/__pycache__/preload_checks.cpython-314.pyc`, `scripts/__pycache__/run_pipeline.cpython-314.pyc`, `scripts/__pycache__/run_quality.cpython-314.pyc` | Python-generated bytecode caches for script modules; disposable runtime artifacts, not source. |
| `docs/logs/README.md` | Local instructions for capturing pre-load pass/failure runs; it explicitly notes the neighboring logs were not regenerated during that prior audit. |
| `docs/logs/preload_fail_duplicate_ts.log`, `docs/logs/preload_fail_missing_column.log`, `docs/logs/preload_fail_negative_demand.log`, `docs/logs/preload_pass.log` | Pre-existing local pre-load run outputs. Treat them as unverified historical logs, not proof of a current run. |

`.git/` contains repository metadata, not application code, and is intentionally
not enumerated. Empty placeholders (`.gitkeep`) and runtime logs do not affect
the pipeline.
