# [Project Title]

End-to-end data engineering pipeline: ingestion, cleaning, PostgreSQL storage, data quality checks, Kestra orchestration, and a BI dashboard.

> **Status:** Phase 1 (environment setup). The dataset and analytical questions are described in `docs/`.

## Team

| Name | ID | Role |
|------|----|------|
| TBD  | TBD | TBD |

## Architecture (planned)

```
[Source] -> [Python Ingestion] -> [PostgreSQL] -> [Kestra Orchestrator] -> [Dashboard]
```

The full diagram is in `docs/`. Only components that are actually implemented are listed as done in the phase table below.

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
├── scripts/             # Extraction and cleaning code
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