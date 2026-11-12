# California Electricity Demand and Weather Analytics

End-to-end data engineering pipeline: ingestion, cleaning, PostgreSQL storage, data quality checks, Kestra orchestration, and a BI dashboard.

> **Status:** Phase 1 (environment setup). The dataset and analytical questions are described in `docs/`.

## Team

| Name | ID | Phase 1 Role |
|------|----|--------------|
| Hisham Wael Hosny | 692300279 | Dataset description & data dictionary |
| Zeyad Mohamed | 692300066 | Docker setup (PostgreSQL, pgAdmin), GitHub repo & submission video |
| Mohamed Mostafa | 692300110 | Architecture diagram |
| Basel Tamer Fathy | 692300055 | Database table design (star schema) |
| Fatma Shrief | 692300201 | Dataset selection, proposal lead, analytical questions (Q1-Q3) |

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

The raw CSV is first loaded as-is into a staging table, then SQL (orchestrated by Kestra) splits it into a star schema.

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

- Docker Desktop (with the WSL 2 backend on Windows) or Docker Engine + Compose v2 on Linux
- Git

Check your setup:

```bash
docker --version
docker compose version
```

## Quick Start

```bash
git clone <repo-url>
cd <repo-folder>

cp .env.example .env      # then edit .env with your own values
docker compose up -d
docker compose ps         # both containers should be Up (postgres: healthy)
```

## Services

| Service  | Image            | URL / Port             |
|----------|------------------|------------------------|
| postgres | postgres:16      | `localhost:5432`       |
| pgadmin  | dpage/pgadmin4   | http://localhost:8080  |

PostgreSQL data is stored in the named volume `pgdata`, so it persists when containers are stopped.

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
```

Note: database credentials are applied only the first time the volume is created. If you change them in `.env` later, run `docker compose down -v` first.

## Project Structure

```
├── docs/                # Proposal, architecture diagrams, data dictionary
├── scripts/             # Extraction, cleaning, and ingestion code (Python)
├── sql/                 # Table schemas (DDL), quality checks, views
├── flows/               # Kestra YAML orchestration flows
├── docker-compose.yml
├── .env.example
└── README.md
```

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Proposal, dataset choice, Docker + PostgreSQL + pgAdmin | In progress |
| 2 | Ingestion and raw storage | Not started |
| 3 | Cleaning, star schema, SQL views | Not started |
| 4 | Data quality checks | Not started |
| 5 | Kestra orchestration, idempotency | Not started |
| 6 | Dashboard, documentation, demo | Not started |

## Security

Credentials live only in `.env`, which is git-ignored. Never commit passwords or tokens. `.env.example` contains placeholder values only.

## AI Usage Disclosure

[Fill in honestly: which parts of this project were created with AI assistance, and confirm that every team member understands and can explain them.]
