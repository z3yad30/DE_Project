import sys
from pathlib import Path

from psycopg2 import sql

from dq_common import CheckResult, DataQualityError, log_results
from load_raw import connect
from logging_config import get_logger


logger = get_logger("run_quality")
SQL_PATH = (
    Path(__file__).resolve().parent.parent
    / "sql"
    / "quality_checks.sql"
)


def run_quality(connection, schema: str = "dw") -> list[CheckResult]:
    """Run post-load checks without taking ownership of the connection."""
    statement = sql.SQL(
        SQL_PATH.read_text(encoding="utf-8")
    ).format(schema=sql.Identifier(schema))

    with connection.cursor() as cursor:
        cursor.execute(statement)
        rows = cursor.fetchall()

    if not rows:
        raise RuntimeError("The quality SQL returned no checks")

    results = []
    for check_name, failed_rows, detail in rows:
        if failed_rows is None:
            raise RuntimeError(
                f"Quality check {check_name!r} returned NULL failed_rows"
            )
        failed_count = int(failed_rows)
        results.append(
            CheckResult(
                name=check_name,
                tier="post-load",
                status="PASS" if failed_count == 0 else "FAIL",
                failed_count=failed_count,
                message=detail,
            )
        )

    log_results(results, logger)
    failures = [result for result in results if result.status == "FAIL"]
    logger.info(
        "DQ SUMMARY [post-load]: %s passed, %s failed",
        len(results) - len(failures),
        len(failures),
    )
    if failures:
        raise DataQualityError(failures)
    return results


def main() -> int:
    connection = None
    try:
        connection = connect()
        run_quality(connection)
        return 0
    except DataQualityError as exc:
        logger.error("DQ ERROR: %s", exc)
        return 1
    except Exception:
        logger.exception("Could not complete post-load quality checks")
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    sys.exit(main())
