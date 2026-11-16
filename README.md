# California Electricity Demand and Weather Analytics

End-to-end data engineering pipeline: ingestion, cleaning, PostgreSQL storage, data quality checks, Kestra orchestration, and a BI dashboard.

> **Project status:** Phase 1 is complete and Phase 2 is in progress. See the [Roadmap](#roadmap).

## Team

| Name | ID | Phase 1 Role | Phase 2 Role |
|------|----|--------------|---------------|
| Hisham Wael Hosny | 692300279 | Dataset description & data dictionary | Raw data profiling and notes |
| Zeyad Mohamed | 692300066 | Docker setup (PostgreSQL, pgAdmin), GitHub repo & submission video | Docker, Compose, integration |
| Mohamed Mostafa | 692300110 | Architecture diagram | Logging, ingest entry point, architecture diagram |
| Basel Tamer Fathy | 692300055 | Database table design (star schema) | Raw schema and loader |
| Fatma Shrief | 692300201 | Dataset selection, proposal lead, analytical questions (Q1-Q3) | Kaggle extraction (`scripts/extract.py`) |

## Dataset

| | |
|---|---|
| Name | CAISO Hourly Demand + Population-Weighted Weather |
| Source | https://www.kaggle.com/datasets/arimancy/caiso-hourly-demand-weather |
| Publisher / License | Arimancy LLC / CC BY 4.0 |
| Size | ~98,968 rows x 35 columns (hourly records) |
| Period | July 2015 to October 2026 |
| Format | Parquet and CSV |
| Demand source | EIA-930 hourly grid data (cleaned by Catalyst Cooperative / PUDL) plus a short recent tail from the EIA API. CAISO covers roughly 80% of California load. |
| Weather source | ERA5 reanalysis (via Open-Meteo) at 7 cities (Los Angeles, Riverside, San Diego, San Francisco, San Jose, Sacramento, Fresno), combined using Census population weights. |

The full data dictionary is in `docs/`.

## Analytical Questions

1. **Temperature effect:** How does temperature affect hourly electricity demand? At what temperature does demand start to go up fast?
2. **Solar and the daily load shape:** How has the midday dip in demand changed from 2015 to 2026 in each season? How do sunshine and cloud cover relate to it?
3. **Calendar and cities:** How do the hour of the day, weekends, and holidays affect peak demand? Which of the 7 cities' temperatures explains demand best?

## Architecture (planned)

```
[Source] -> [Python Ingestion] -> [PostgreSQL] -> [Kestra Orchestrator] -> [Dashboard]
```

The full diagram is in `docs/`. Only components that are actually implemented are listed as done in the phase table below.

## Planned Database Tables

The raw CSV is intended to be loaded as-is into a staging table, then SQL (orchestrated by Kestra) can split it into a star schema.

| Table | Type | Description |
|-------|------|-------------|
| `raw_caiso_hourly` | Staging | All 35 original CSV columns, untouched raw copy |
| `dim_datetime` | Dimension | Timestamps, year, month, day of week, hour, season, weekend / DST flags |
| `dim_holiday` | Dimension | Statutory and observed holiday flags (federal and CA) |
| `dim_city` | Dimension | City name and population weight (7 cities) |
| `fact_demand` | Fact | Demand values, imputation code and flags, demand source |
| `fact_city_temperature` | Fact | Temperature per city per hour (reshaped wide to long) |
| `fact_weather_weighted` | Fact | Population-weighted temperature, radiation, cloud cover, HDH/CDH, HDD/CDD, quality flags |

## Prerequisites

- Docker Desktop (with the WSL 2 backend on Windows) or Docker Engine + Compose v2
- Git

No local Python installation or virtual environment is needed.

Check your Docker setup:

```bash
docker --version
docker compose version
```

## Quick Start

```bash
git clone https://github.com/z3yad30/DE_Project.git
cd DE_Project
cp .env.example .env
```

Edit `.env` and fill in `KAGGLE_USERNAME` and `KAGGLE_KEY`. Find both in your Kaggle account under **Settings -> API**; create an API token if needed. Keep these credentials private.

```bash
docker compose up -d
docker compose ps
docker compose run --rm ingest
```

The downloaded CSV appears in `./data/raw/`. This directory is git-ignored.

## How dependencies work (no virtualenv)

The Docker image installs dependencies from `scripts/requirements.txt` at build time. To add a package, add it to that file and rebuild the image:

```bash
docker compose build ingest
```

Code changes also require rebuilding the image with `docker compose build ingest`, or run the service with `docker compose run --rm --build ingest`.

## Services

| Service | Image | URL / Port | How it runs |
|---------|-------|------------|-------------|
| postgres | postgres:16 | `localhost:5432` | Started by `docker compose up -d` |
| pgadmin | dpage/pgadmin4 | http://localhost:8080 | Started by `docker compose up -d` |
| ingest | `scripts/Dockerfile` | On demand | Profile `ingest`; run with `docker compose run --rm ingest` |

The `ingest` profile keeps the service out of the default `docker compose up -d` startup. PostgreSQL data is stored in the named volume `pgdata`, so it persists when containers are stopped.

## Notes for Windows / WSL

Run Docker commands from the repository folder inside WSL. Files created by the container in `data/raw` may be owned by root; fix ownership with:

```bash
sudo chown -R $USER data
```

## Connecting pgAdmin to PostgreSQL

1. Open http://localhost:8080 and log in with `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` from your `.env`.
2. Right-click **Servers** -> **Register** -> **Server**.
3. **General -> Name:** any name (e.g. `pipeline`).
4. **Connection:**
   - Host: `postgres` (the service name, **not** `localhost`, because pgAdmin runs inside a container)
   - Port: `5432`
   - Maintenance database: value of `POSTGRES_DB`
   - Username / Password: `POSTGRES_USER` / `POSTGRES_PASSWORD`
5. Save. The database should appear under **Databases**.

## Useful Commands

```bash
docker compose logs -f postgres   # follow Postgres logs
docker compose down               # stop containers, keep data
docker compose down -v            # stop containers AND delete the data volume
docker compose run --rm ingest    # run ingestion on demand
docker compose build ingest       # build the ingestion image
```

Note: database credentials are applied only the first time the volume is created. If you change them in `.env` later, run `docker compose down -v` first.

## Project Structure

```
├── data/
│   └── raw/                      # Downloaded raw CSV files (git-ignored)
├── docs/                         # Proposal, architecture diagrams, data dictionary
├── scripts/
│   ├── Dockerfile
│   ├── extract.py
│   └── requirements.txt
├── sql/                          # Table schemas (DDL), quality checks, views
├── flows/                        # Kestra YAML orchestration flows
├── .dockerignore
├── docker-compose.yml
├── .env.example
└── README.md
```

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Proposal, dataset choice, Docker + PostgreSQL + pgAdmin | Done |
| 2 | Ingestion and raw storage | In progress |
| 3 | Cleaning, star schema, SQL views | Not started |
| 4 | Data quality checks | Not started |
| 5 | Kestra orchestration, idempotency | Not started |
| 6 | Dashboard, documentation, demo | Not started |

## Phase 2: Ingestion and Raw Storage

### Ingestion script
<!-- MOHAMED:START -->
<!-- MOHAMED:END -->
### Raw storage
<!-- BASEL:START -->
The raw layer stores each CSV row as received, without cleaning, casting, trimming, deduplicating, or reordering. Source columns are `TEXT` so PostgreSQL does not reinterpret or alter the CSV values; transformations belong in later phases.

The schema is `raw_data`. It contains `raw_data.raw_caiso_hourly` for the CSV rows and `raw_data.ingestion_log` for ingestion traceability.

| Metadata column | Purpose |
|---|---|
| `_batch_id` | Identifies the ingestion batch |
| `_source_file` | Records the source CSV filename |
| `_ingested_at` | Records when the row was loaded |

Every load appends a new batch. Duplicate handling is planned for Phase 5.

Set `POSTGRES_USER` and `POSTGRES_DB` in your shell to the corresponding values from `.env`, then run the proof queries from the repository root:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < sql/02_raw_proof.sql
```

In pgAdmin, open **Servers → your registered server → Databases → your database → Schemas → raw_data → Tables** to inspect `raw_caiso_hourly` and `ingestion_log`.
<!-- BASEL:END -->
### Data profiling
<!-- HISHAM:START -->
<!-- HISHAM:END -->

## Security

Credentials live only in `.env`, which is git-ignored. Never commit passwords or tokens. `.env.example` contains placeholder values only.

