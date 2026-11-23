# Phase 3 In-Person Lab Demo Checklist

Run commands from the repository root in the configured Compose project. The
clean pipeline was validated against the existing 98,968-row successful raw
batch. Kaggle ingestion was not run in this audit because it would transmit
`.env` credentials to Kaggle.

## Live demo

1. **Start PostgreSQL and pgAdmin.**

   Command:

   ```bash
   docker compose up -d
   docker compose ps
   ```

   Say: “The database starts first; `ingest` and `clean` are on-demand
   profiled services, not long-running containers.”

   Expect: `postgres` is healthy and `pgadmin` is running. `clean` and `ingest`
   are not started by the default `up -d`.

2. **Ingest the latest Kaggle CSV.**

   Command:

   ```bash
   docker compose run --rm ingest
   ```

   Say: “Ingestion stores the original CSV and appends its raw text values.
   The command requires valid Kaggle credentials in `.env`.”

   Expect: **NOT VERIFIED in this audit.** The command was intentionally not
   executed because it would transmit `.env` credentials to Kaggle. On a
   successful first load, expect a `SUCCESS` ingestion summary with fetched
   and loaded row counts; an identical file may instead be `SKIPPED`.

3. **Run cleaning, the pre-load checks, the warehouse load, and post-load checks.**

   Command:

   ```bash
   docker compose run --rm --build clean
   ```

   Say: “One connection and transaction cover the cleaning-stage load,
   warehouse refresh, and both quality tiers. The warehouse commits only
   after every post-load check passes.”

   Expect: a selected successful raw batch; before/after row counts; all
   pre-load and post-load checks report `PASS`; the final
   `PIPELINE SUMMARY` reports `status=SUCCESS`.

4. **Inspect warehouse tables, keys, and raw-to-clean row counts.**

   Load the database values for the `psql` commands:

   ```bash
   set -a
   . ./.env
   set +a
   ```

   Commands:

   ```bash
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt dw.*'
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
   WITH latest AS (
       SELECT log.batch_id
       FROM raw_data.ingestion_log AS log
       WHERE log.status = 'SUCCESS'
         AND EXISTS (
             SELECT 1
             FROM raw_data.raw_caiso_hourly AS raw
             WHERE raw._batch_id = log.batch_id
         )
       ORDER BY log.finished_at DESC NULLS LAST,
                log.started_at DESC NULLS LAST,
                log.batch_id DESC
       LIMIT 1
   )
   SELECT
       latest.batch_id,
       (SELECT COUNT(*) FROM raw_data.raw_caiso_hourly raw
        WHERE raw._batch_id = latest.batch_id) AS raw_rows,
       (SELECT COUNT(*) FROM clean_data.stg_caiso_clean clean
        WHERE clean._batch_id = latest.batch_id) AS clean_rows,
       (SELECT COUNT(*) FROM dw.dim_datetime) AS dim_datetime_rows,
       (SELECT COUNT(*) FROM dw.fact_demand) AS fact_demand_rows,
       (SELECT COUNT(*) FROM dw.fact_weather_weighted) AS fact_weather_rows,
       (SELECT COUNT(*) FROM dw.dim_city) AS dim_city_rows,
       (SELECT COUNT(*) FROM dw.fact_city_temperature) AS city_temperature_rows
   FROM latest;

   SELECT
       tc.table_name,
       tc.constraint_type,
       tc.constraint_name,
       string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position)
           AS columns,
       CASE WHEN tc.constraint_type = 'FOREIGN KEY' THEN (
           SELECT string_agg(
               ccu.table_name || '.' || ccu.column_name,
               ', ' ORDER BY ccu.table_name, ccu.column_name
           )
           FROM information_schema.constraint_column_usage ccu
           WHERE ccu.constraint_catalog = tc.constraint_catalog
             AND ccu.constraint_schema = tc.constraint_schema
             AND ccu.constraint_name = tc.constraint_name
       ) END AS referenced_columns
   FROM information_schema.table_constraints tc
   JOIN information_schema.key_column_usage kcu
     ON kcu.constraint_catalog = tc.constraint_catalog
    AND kcu.constraint_schema = tc.constraint_schema
    AND kcu.constraint_name = tc.constraint_name
   WHERE tc.constraint_schema = 'dw'
     AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
   GROUP BY
       tc.constraint_catalog,
       tc.constraint_schema,
       tc.table_name,
       tc.constraint_type,
       tc.constraint_name
   ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;
   SQL
   ```

   Say: “The timestamp dimension and hourly facts should match the latest
   successful raw batch. City temperature has seven rows per clean hour.”

   Expect: `raw_rows`, `clean_rows`, `dim_datetime_rows`, `fact_demand_rows`,
   and `fact_weather_rows` match; `dim_city_rows` is `7`; city temperatures
   equal seven times the clean rows. The key listing shows each primary and
   foreign key defined in the warehouse schema.

5. **Create and query the Q1, Q2, and Q3 views.**

   Commands:

   ```bash
   docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < sql/06_views_q1.sql
   docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < sql/07_views_q2.sql
   docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < sql/08_views_q3.sql
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT * FROM dw.v_q1_demand_by_temp_bin ORDER BY temp_bin_c LIMIT 5;'
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT * FROM dw.v_q1_demand_slope ORDER BY temp_bin_c LIMIT 5;'
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT * FROM dw.v_q2_load_shape_by_year_season_hour ORDER BY year, season, local_hour LIMIT 5;'
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT * FROM dw.v_q2_midday_dip ORDER BY year, season LIMIT 5;'
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT * FROM dw.v_q3_peak_by_hour_weekend_holiday ORDER BY local_hour LIMIT 5;'
   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT * FROM dw.v_q3_city_temp_demand_corr ORDER BY correlation_rank LIMIT 5;'
   ```

   Say: “Q1 bins demand by two-degree temperature intervals and compares each
   average with the previous bin. Q2 compares hourly load shape and the midday
   dip; Q3 groups calendar peaks and ranks city-temperature correlations.”

   Expect: each view query returns rows. The first Q1 rows are recorded in
   `docs/phase3_notes.md`.

6. **Run cleaning again to demonstrate the full-refresh result.**

   Command:

   ```bash
   docker compose run --rm clean
   ```

   Say: “Cleaning rebuilds staging and the warehouse from the selected raw
   batch; it is not the SHA-256 skip behavior used by ingestion.”

   Expect: `status=SUCCESS`; the second summary has the same raw, clean, and
   warehouse counts as the first successful run.

7. **Demonstrate a pre-load failure.**

   Command:

   ```bash
   set +e
   docker compose run --rm --no-deps clean python scripts/demo_preload_fail.py --case negative_demand
   result=$?
   set -e
   printf 'exit code: %s\n' "$result"
   ```

   Say: “The demo corrupts only an in-memory copy of the clean DataFrame. It
   does not write the injected value to staging or the warehouse.”

   Expect: `demand_mwh_positive` fails, the process exits `1`, and no staging
   load or warehouse stages run.

8. **Demonstrate a post-load failure on `dw_test`.**

   Command:

   ```bash
   set +e
   docker compose run --rm --no-deps clean python scripts/demo_quality_fail.py --case negative_demand
   result=$?
   set -e
   printf 'exit code: %s\n' "$result"
   ```

   Say: “The demo copies the warehouse into an unconstrained `dw_test`
   schema, corrupts that copy, runs the same checks, and drops the schema in
   `finally`. The real `dw` tables are not modified.”

   Expect: the negative-demand check fails, the process exits `1`, and the
   log confirms that `dw_test` was dropped.

## Questions you will be asked

1. **How is cleaning different from ingestion?** Ingestion skips identical
   files by SHA-256. Cleaning rebuilds staging and the warehouse from the
   selected raw batch on each run.
2. **What happens when a quality check fails?** The pipeline logs the stage
   and check errors, rolls back the transaction, skips later stages, and
   returns exit code `1`.
3. **Why are the quality checks split into two tiers?** Pre-load checks catch
   malformed or invalid clean data before writing it; post-load SQL checks
   verify warehouse keys, relationships, ranges, and row counts.
4. **Why does the post-load demo use `dw_test`?** Its copied tables have no
   constraints, so intentional corruptions can be inserted without changing
   the real warehouse.
5. **Why does the pipeline use one connection?** Staging, warehouse rebuild,
   and post-load validation share one transaction, so a failed check cannot
   leave a partially refreshed warehouse.
