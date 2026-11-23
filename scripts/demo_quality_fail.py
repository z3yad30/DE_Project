
from dq_common import DataQualityError
from load_raw import connect
from logging_config import get_logger
from run_quality import execute_checks


logger = get_logger("demo_quality_fail")


def create_test_schema(connection):
    """Create an unconstrained schema with deliberately invalid data."""

    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS dw_test CASCADE")
        cursor.execute("CREATE SCHEMA dw_test")

        cursor.execute("""
            CREATE TABLE dw_test.dim_holiday (
                holiday_id INTEGER,
                is_holiday BOOLEAN,
                is_weekend BOOLEAN
            )
        """)

        cursor.execute("""
            CREATE TABLE dw_test.dim_datetime (
                datetime_id INTEGER,
                month INTEGER,
                hour INTEGER,
                day_of_week INTEGER,
                holiday_id INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE dw_test.dim_city (
                city_id INTEGER,
                city_name TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE dw_test.fact_demand (
                datetime_id INTEGER,
                demand_mwh NUMERIC,
                demand_reported_mwh NUMERIC,
                demand_imputed_pudl_mwh NUMERIC
            )
        """)

        cursor.execute("""
            CREATE TABLE dw_test.fact_weather_weighted (
                datetime_id INTEGER,
                shortwave_radiation_pop_wt_wm2 NUMERIC,
                cloud_cover_pop_wt_pct NUMERIC,
                hdh_65 NUMERIC,
                cdh_65 NUMERIC,
                hdd_65_daily NUMERIC,
                cdd_65_daily NUMERIC
            )
        """)

        cursor.execute("""
            CREATE TABLE dw_test.fact_city_temperature (
                datetime_id INTEGER,
                city_id INTEGER,
                temp_c NUMERIC
            )
        """)

        # Duplicate primary keys and invalid holiday data.
        cursor.execute("""
            INSERT INTO dw_test.dim_holiday VALUES
                (1, TRUE, FALSE),
                (1, FALSE, TRUE)
        """)

        # Duplicate datetime IDs, invalid date values,
        # and a reference to a nonexistent holiday.
        cursor.execute("""
            INSERT INTO dw_test.dim_datetime VALUES
                (100, 13, 25, 8, 999),
                (100, 0, -1, -1, 999)
        """)

        # Duplicate city IDs.
        cursor.execute("""
            INSERT INTO dw_test.dim_city VALUES
                (1, 'Cairo'),
                (1, 'Alexandria')
        """)

        # Duplicate fact keys, negative demand, and excessive NULLs.
        cursor.execute("""
            INSERT INTO dw_test.fact_demand VALUES
                (100, -50, NULL, NULL),
                (100, 100, NULL, NULL)
        """)

        # Duplicate fact keys, invalid cloud cover,
        # negative measurements, and excessive NULLs.
        cursor.execute("""
            INSERT INTO dw_test.fact_weather_weighted VALUES
                (100, -10, 150, -5, -3, NULL, NULL),
                (100, 20, 50, 10, 10, NULL, NULL)
        """)

        # Duplicate composite keys and nonexistent references.
        cursor.execute("""
            INSERT INTO dw_test.fact_city_temperature VALUES
                (100, 999, 25),
                (100, 999, 30)
        """)

    connection.commit()
    logger.info("Created dw_test schema with intentionally invalid data")


def run_failure_demo():
    """Run quality checks and verify that failures are detected."""

    connection = connect()

    try:
        create_test_schema(connection)

        results = execute_checks(
            connection,
            schema="dw_test",
            include_row_counts=False,
        )

        failures = [
            result for result in results
            if not result.passed
        ]

        if not failures:
            raise DataQualityError(
                "Demo failed: no quality issues were detected"
            )

        logger.info(
            "SUCCESS: Demo detected %s failing checks out of %s",
            len(failures),
            len(results),
        )

        for failure in failures:
            logger.info(
                "DETECTED FAILURE: %s",
                failure.rule_name,
            )

    finally:
        try:
            connection.rollback()

            with connection.cursor() as cursor:
                cursor.execute(
                    "DROP SCHEMA IF EXISTS dw_test CASCADE"
                )

            connection.commit()
            logger.info("Cleaned up dw_test schema")

        finally:
            connection.close()


def main():
    try:
        run_failure_demo()
        return 0

    except Exception:
        logger.exception("Failure demonstration could not complete")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
