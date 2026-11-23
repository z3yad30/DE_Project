import sys
import time
from pathlib import Path

from clean import clean_batch, load_staging
from load_raw import connect
from logging_config import get_logger
from preload_checks import run_preload_checks
from run_quality import run_quality


logger = get_logger("run_pipeline")
SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
DW_TABLES = (
    "dim_datetime",
    "dim_holiday",
    "dim_city",
    "fact_demand",
    "fact_weather_weighted",
    "fact_city_temperature",
)


def execute_sql_file(connection, filename: str) -> None:
    sql_path = SQL_DIR / filename
    with connection.cursor() as cursor:
        cursor.execute(sql_path.read_text(encoding="utf-8"))


def get_dw_counts(connection) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                to_regclass('dw.dim_datetime') IS NOT NULL,
                to_regclass('dw.dim_holiday') IS NOT NULL,
                to_regclass('dw.dim_city') IS NOT NULL,
                to_regclass('dw.fact_demand') IS NOT NULL,
                to_regclass('dw.fact_weather_weighted') IS NOT NULL,
                to_regclass('dw.fact_city_temperature') IS NOT NULL
            """
        )
        if not all(cursor.fetchone()):
            return "unavailable"

        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM dw.dim_datetime),
                (SELECT COUNT(*) FROM dw.dim_holiday),
                (SELECT COUNT(*) FROM dw.dim_city),
                (SELECT COUNT(*) FROM dw.fact_demand),
                (SELECT COUNT(*) FROM dw.fact_weather_weighted),
                (SELECT COUNT(*) FROM dw.fact_city_temperature)
        """)
        counts = cursor.fetchone()

    return ",".join(
        f"{table}={count}"
        for table, count in zip(DW_TABLES, counts)
    )


def run_pipeline() -> int:
    started_at = time.perf_counter()
    connection = None
    stage = "connect"
    status = "FAILED"
    rows_raw = "not-run"
    rows_clean = "not-run"
    dw_counts = "unavailable"

    try:
        connection = connect()

        stage = "clean"
        logger.info("PIPELINE STAGE start=%s", stage)
        dataframe, stats = clean_batch(connection)
        rows_raw = stats.rows_before
        rows_clean = stats.rows_after
        logger.info(
            "Pipeline cleaning stats rows_raw=%s rows_clean=%s "
            "exact_duplicates_removed=%s",
            rows_raw,
            rows_clean,
            stats.exact_duplicates_removed,
        )

        stage = "preload_checks"
        logger.info("PIPELINE STAGE start=%s", stage)
        run_preload_checks(dataframe, expected_raw_rows=stats.rows_before)

        stage = "staging_load"
        logger.info("PIPELINE STAGE start=%s", stage)
        load_staging(connection, dataframe)

        stage = "warehouse_schema"
        logger.info("PIPELINE STAGE start=%s", stage)
        execute_sql_file(connection, "04_schema_dw.sql")

        stage = "warehouse_load"
        logger.info("PIPELINE STAGE start=%s", stage)
        execute_sql_file(connection, "05_load_dw.sql")

        stage = "postload_checks"
        logger.info("PIPELINE STAGE start=%s", stage)
        run_quality(connection)

        stage = "commit"
        connection.commit()
        status = "SUCCESS"
    except Exception as exc:
        status = "FAILED"
        logger.exception("Pipeline stage=%s failed: %s", stage, exc)
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                logger.exception("Pipeline rollback failed after stage=%s", stage)
    finally:
        if connection is not None:
            try:
                dw_counts = get_dw_counts(connection)
            except Exception:
                logger.exception("Could not read warehouse counts for summary")
                dw_counts = "unavailable"
            try:
                connection.close()
            except Exception:
                status = "FAILED"
                logger.exception("Could not close the pipeline connection")

        logger.info(
            "PIPELINE SUMMARY status=%s rows_raw=%s rows_clean=%s "
            "dw_counts=%s seconds=%.3f",
            status,
            rows_raw,
            rows_clean,
            dw_counts,
            time.perf_counter() - started_at,
        )

    return 0 if status == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(run_pipeline())
