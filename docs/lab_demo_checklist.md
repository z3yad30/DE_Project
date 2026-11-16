# Phase 2 In-Person Lab Demo Checklist

Run the commands from the repository root. Before presenting, confirm `.env` contains working Kaggle credentials and that Docker Compose is available. The tested dataset contained 98,968 rows; the output may differ if the Kaggle dataset changes.

## Live demo

1. **Start the database and pgAdmin.**

   Command:

   ```bash
   docker compose up -d
   ```

   Say: “This starts the database and its admin interface; ingestion is an on-demand service.”

   Expect: Compose starts PostgreSQL, waits for its healthcheck, then starts pgAdmin.

2. **Check service readiness.**

   Command:

   ```bash
   docker compose ps
   ```

   Say: “The database must be healthy before ingestion can connect.”

   Expect: `postgres` reports `healthy` and `pgadmin` is running; `ingest` is not listed as a continuously running service.

3. **Run the containerized ingestion live.**

   Command:

   ```bash
   docker compose run --rm ingest
   ```

   Say: “The one-off container downloads the Kaggle archive, extracts an unchanged CSV, checks its checksum, and loads new rows into the raw table.”

   Expect on a first successful load: log lines include `START batch=...`, `Records fetched: 98968`, `Records loaded into raw_data.raw_caiso_hourly: 98968`, and `SUMMARY ... status=SUCCESS http=200 fetched=98968 loaded=98968`. If that file was already loaded successfully, expect `SKIP` and `status=SKIPPED` instead. The container's log output appears in this terminal.

4. **Show the raw CSV files stored on the host.**

   Command:

   ```bash
   ls -lh data/raw
   ```

   Say: “These are the original CSV files written to the host folder through the container's bind mount; the loader does not remove them.”

   Expect: one or more timestamped `caiso_hourly_*.csv` files. In validation, each file was 29,076,559 bytes and was owned by `root:root`.

5. **Show the database row count and run status.**

   Commands:

   ```bash
   set -a
   . ./.env
   set +a
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "SELECT count(*) AS total_rows FROM raw_data.raw_caiso_hourly;"
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "SELECT status, http_status, rows_fetched, rows_loaded FROM raw_data.ingestion_log ORDER BY started_at DESC LIMIT 5;"
   ```

   Say: “The raw table stores the source values as text, while the ingestion log records the batch outcome and row counts.”

   Expect after the first validated load: `total_rows` is `98968`, with a `SUCCESS` row showing HTTP `200`, `98968` fetched, and `98968` loaded.

6. **Optionally inspect the table in pgAdmin.**

   Action: open [http://localhost:8080](http://localhost:8080), sign in using `PGADMIN_EMAIL` and `PGADMIN_PASSWORD`, and register the PostgreSQL server with host `postgres`, port `5432`, maintenance database `POSTGRES_DB`, and the `POSTGRES_USER` / `POSTGRES_PASSWORD` values. Browse **Servers -> your server -> Databases -> your database -> Schemas -> raw_data -> Tables -> raw_caiso_hourly -> View/Edit Data -> All Rows**.

   Say: “The pgAdmin container reaches PostgreSQL using its Compose service name, `postgres`.”

   Expect: rows from `raw_data.raw_caiso_hourly`. The login page was verified, but registration and table browsing were not exercised in this validation; alternatively, repeat step 4 to show the host CSV.

7. **Try the requested wrong-key failure demo.**

   Command:

   ```bash
   set +e
   docker compose run --rm -e KAGGLE_KEY=deliberately_wrong_for_demo ingest
   result=$?
   set -e
   printf 'exit code: %s\n' "$result"
   ```

   Say: “If Kaggle rejects this key with HTTP 401, the run should be `FAILED`, return exit code `1`, and log `http_status=401`.”

   Expected only when the Kaggle endpoint actually returns 401: `SUMMARY ... status=FAILED http=401 ...`, exit code `1`, and a `FAILED` row with `http_status=401` in `raw_data.ingestion_log`.

   **Validation limitation:** this failure case was not reproduced against the public dataset endpoint. Even with the explicit bad-key override, Kaggle returned HTTP `200`, the file was downloaded, and the run was `SKIPPED`; do not present a 401 as demonstrated unless the live run actually returns it. A verified failure alternative is to clear both credentials for one command:

   ```bash
   set +e
   docker compose run --rm -e KAGGLE_USERNAME= -e KAGGLE_KEY= ingest
   result=$?
   set -e
   printf 'exit code: %s\n' "$result"
   ```

   This produced `FAILED`, exit code `1`, `http=None`, and an ingestion-log row with an empty `http_status`; it verifies failure handling but is not a 401 demo.

8. **Run ingestion again to show the SHA-256 skip.**

   Command:

   ```bash
   docker compose run --rm ingest
   ```

   Say: “The loader skips identical content already marked successful, but extraction still downloads and keeps a new timestamped CSV.”

   Expect for the unchanged dataset: `Records fetched: 98968`, `SKIP: this exact file was already loaded`, and `SUMMARY ... status=SKIPPED http=200 fetched=98968 loaded=0`; the process exits `0`. In validation, the two successful runs left two CSV files in `data/raw/`, each 29,076,559 bytes, while the raw table still contained one 98,968-row batch.

9. **Show the latest outcomes after the failure and skip demonstrations.**

   Command:

   ```bash
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "SELECT status, http_status, rows_fetched, rows_loaded, error FROM raw_data.ingestion_log ORDER BY started_at DESC LIMIT 5;"
   ```

   Say: “Each automated attempt is recorded with its status and available HTTP and row-count metadata.”

   Expect: latest rows show `SKIPPED` for a repeated file and `FAILED` for a missing-credentials failure if that alternative was run; a bad-key row with HTTP 401 appears only if Kaggle actually returned 401.

## Questions you will be asked

1. **Why is raw data preserved?** The CSV is extracted unchanged to `data/raw/` and the loader appends source values without modifying or deleting the file.
2. **Why are all source columns `TEXT`?** The schema and loader use `TEXT` for the 35 CSV fields so PostgreSQL does not reinterpret source values before a later transformation step; ingestion metadata has separate types.
3. **Why use host `postgres` instead of `localhost`?** Inside the Compose network, `postgres` resolves to the database service while `localhost` points back to the connecting container.
4. **What does the bind mount do?** Compose maps host `./data/raw` to container `/data/raw` so the extracted CSV remains available on the host.
5. **Why copy `requirements.txt` before the code in the Dockerfile?** The dependency installation layer can be reused after code-only edits because the requirements file is copied and installed first.
6. **What do the healthcheck and `depends_on` do?** PostgreSQL's `pg_isready` healthcheck reports readiness, and `depends_on: condition: service_healthy` makes pgAdmin and ingestion wait for a healthy database.
7. **Why exponential retries, but not for 401/403/404?** The extractor retries temporary connection, timeout, and server errors with `2 ** attempt` delays, while authentication, access, and not-found responses fail immediately.
8. **What is the exit code used for?** The entry point returns `0` for `SUCCESS` or `SKIPPED` and `1` for `FAILED` so a shell or automation can distinguish failure.
9. **Why store a SHA-256?** The checksum identifies identical downloaded file content for the prior-`SUCCESS` skip check.
10. **What is the batch ID for?** The batch ID links rows appended by one load to that run's metadata and ingestion-log record.
