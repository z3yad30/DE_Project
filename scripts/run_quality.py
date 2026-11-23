
import logging
import re
import sys
from pathlib import Path

from dq_common import CheckResult, DataQualityError
from load_raw import connect
from logging_config import get_logger


logger = get_logger("run_quality")

SQL_PATH = (
    Path(__file__).resolve().parent.parent
    / "sql"
    / "quality_checks.sql"
)

NULL_THRESHOLDS = {
    "demand_reported_null_pct": 1.0,
    "demand_imputed_null_pct": 2.0,
    "hdd_daily_null_pct": 0.1,
    "cdd_daily_null_pct": 0.1,
}

DEFAULT_THRESHOLD = 0


def load_checks(schema="dw", include_row_counts=True):
    """Load and split the SQL quality checks."""
    sql_text = SQL_PATH.read_text(encoding="utf-8")

    # Remove SQL comments.
    sql_text = re.sub(r"--.*?$", "", sql_text, flags=re.MULTILINE)

    if schema not in ("dw", "dw_test"):
        raise ValueError("Unsupported schema")

    # Allow the failure demo to run against its separate test schema.
    if schema == "dw_test":
        sql_text = sql_text.replace("dw.", "dw_test.")

    statements = [
        statement.strip()
        for statement in sql_text.split(";")
        if statement.strip()
    ]

    # Staging-to-warehouse count checks are not relevant to the demo.
    if not include_row_counts:
        statements = [
            statement
            for statement in statements
            if not re.search(
                r"SELECT\s+'staging_vs_",
                statement,
                re.IGNORECASE,
            )
        ]

    if not statements:
        raise ValueError("No SQL checks found")

    return statements


def execute_checks(connection, schema="dw", include_row_counts=True):
    """Execute quality checks and collect their results."""
    results = []

    for statement in load_checks(schema, include_row_counts):
        with connection.cursor() as cursor:
            cursor.execute(statement)
            row = cursor.fetchone()

        if row is None:
            raise ValueError("A quality check returned no result")

        check_name, offending_count = row

        if offending_count is None:
            raise ValueError(
                f"Quality check '{check_name}' returned NULL"
            )

        # PostgreSQL numeric values may arrive as Decimal.
        # Convert them before comparing with Python thresholds.
        if check_name in NULL_THRESHOLDS:
            offending_count = float(offending_count)
        else:
            offending_count = int(offending_count)

        threshold = NULL_THRESHOLDS.get(
            check_name,
            DEFAULT_THRESHOLD,
        )

        passed = offending_count <= threshold

        result = CheckResult(
            rule_name=check_name,
            passed=passed,
            offending_count=offending_count,
            threshold=threshold,
            message=(
                f"{check_name}: observed={offending_count}, "
                f"allowed={threshold}"
            ),
        )

        results.append(result)

        if result.passed:
            logger.info(
                "PASS | %s | observed=%s | threshold=%s",
                result.rule_name,
                result.offending_count,
                result.threshold,
            )
        else:
            logger.error(
                "FAIL | %s | observed=%s | threshold=%s",
                result.rule_name,
                result.offending_count,
                result.threshold,
            )

    return results


def run_quality_checks():
    """Run all warehouse checks and fail if any check fails."""
    connection = connect()

    try:
        results = execute_checks(connection)
        failures = [
            result for result in results
            if not result.passed
        ]

        if failures:
            raise DataQualityError(
                f"{len(failures)} of {len(results)} "
                "post-load quality checks failed"
            )

        logger.info(
            "All %s post-load quality checks passed",
            len(results),
        )

        return results

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def main() -> int:
    try:
        run_quality_checks()
        return 0

    except DataQualityError as exc:
        logger.error("DATA QUALITY FAILURE: %s", exc)
        return 1

    except Exception:
        logger.exception(
            "Could not complete post-load quality checks"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
