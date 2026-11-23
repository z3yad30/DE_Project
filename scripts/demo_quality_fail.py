import argparse
import sys

from psycopg2 import sql

from dq_common import DataQualityError
from load_raw import connect
from logging_config import get_logger
from run_quality import run_quality


logger = get_logger("demo_quality_fail")
TEST_SCHEMA = "dw_test"
DW_TABLES = (
    "dim_holiday",
    "dim_datetime",
    "dim_city",
    "fact_demand",
    "fact_weather_weighted",
    "fact_city_temperature",
)


def create_test_schema(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(TEST_SCHEMA)
            )
        )
        cursor.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(TEST_SCHEMA))
        )
        for table_name in DW_TABLES:
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE {}.{} AS TABLE {}.{} WITH NO DATA"
                ).format(
                    sql.Identifier(TEST_SCHEMA),
                    sql.Identifier(table_name),
                    sql.Identifier("dw"),
                    sql.Identifier(table_name),
                )
            )
            cursor.execute(
                sql.SQL("INSERT INTO {}.{} SELECT * FROM {}.{}").format(
                    sql.Identifier(TEST_SCHEMA),
                    sql.Identifier(table_name),
                    sql.Identifier("dw"),
                    sql.Identifier(table_name),
                )
            )
    # CREATE TABLE AS copies columns and data, but not constraints.


def corrupt_test_schema(connection, case: str) -> None:
    with connection.cursor() as cursor:
        if case == "duplicate_pk":
            cursor.execute("""
                INSERT INTO dw_test.dim_city
                SELECT * FROM dw_test.dim_city
                LIMIT 1
            """)
        elif case == "negative_demand":
            cursor.execute("""
                UPDATE dw_test.fact_demand
                SET demand_mwh = -1
                WHERE ctid = (
                    SELECT ctid FROM dw_test.fact_demand LIMIT 1
                )
            """)
        elif case == "orphan_fk":
            cursor.execute("""
                UPDATE dw_test.fact_city_temperature AS temperature
                SET city_id = (
                    SELECT COALESCE(MAX(city_id), 0) + 1
                    FROM dw_test.dim_city
                )
                WHERE (temperature.datetime_id, temperature.city_id) = (
                    SELECT datetime_id, city_id
                    FROM dw_test.fact_city_temperature
                    LIMIT 1
                )
            """)
        elif case == "null_spike":
            cursor.execute("""
                UPDATE dw_test.fact_demand
                SET demand_reported_mwh = NULL
            """)
        else:
            raise ValueError(f"Unsupported failure case: {case}")

        if cursor.rowcount == 0:
            raise RuntimeError(
                f"Cannot apply {case}: the copied warehouse has no target rows"
            )


def run_failure_demo(case: str) -> int:
    connection = connect()
    try:
        create_test_schema(connection)
        corrupt_test_schema(connection, case)

        try:
            run_quality(connection, schema=TEST_SCHEMA)
        except DataQualityError as exc:
            if not exc.failed_results:
                raise
            logger.error("DEMO DETECTED [%s]: %s", case, exc)
            return 1

        raise RuntimeError(
            f"Injected {case} corruption was not detected"
        )
    finally:
        try:
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(TEST_SCHEMA)
                    )
                )
            connection.commit()
            logger.info("Dropped test schema %s", TEST_SCHEMA)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Demonstrate post-load quality failures on a copy of dw"
    )
    parser.add_argument(
        "--case",
        required=True,
        choices=[
            "duplicate_pk",
            "negative_demand",
            "orphan_fk",
            "null_spike",
        ],
    )
    args = parser.parse_args()

    try:
        return run_failure_demo(args.case)
    except Exception:
        logger.exception("Failure demonstration could not complete")
        return 1


if __name__ == "__main__":
    sys.exit(main())
