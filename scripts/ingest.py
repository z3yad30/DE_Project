
import os
import csv
import sys
import uuid
import time
from datetime import datetime, timezone

from logging_config import get_logger
from extract import fetch_source
from load_raw import (
    ensure_schema,
    already_loaded,
    load_csv,
    record_run
)

logger = get_logger("ingest")

RAW_DIR = os.environ.get("RAW_DIR", "data/raw")


def get_http_status(error):
    for candidate in (error, error.__cause__):
        response = getattr(candidate, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)
            if status_code is not None:
                return status_code
    return None


def count_csv_rows(csv_path):
    """Count CSV data rows without counting the header."""
    with open(csv_path, "r", newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader, None)  # Skip the header
        return sum(1 for row in reader)


def main():
    batch_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc)
    start_time = time.time()

    status = "SUCCESS"
    http_status = None
    source_file = None
    sha256 = None
    rows_fetched = 0
    rows_loaded = 0
    error_message = None
    exit_code = 0

    logger.info("START batch=%s", batch_id)

    try:
        # 1. Create the database schema and tables
        ensure_schema()

        # 2. Download and save the raw dataset
        result = fetch_source(RAW_DIR)

        source_file = os.path.basename(result.path)
        sha256 = result.sha256
        http_status = result.http_status

        # 3. Count the rows in the downloaded CSV
        rows_fetched = count_csv_rows(result.path)
        logger.info("Records fetched: %s", rows_fetched)

        # 4. Check whether this exact file was already loaded
        if already_loaded(result.sha256):
            logger.info("SKIP: this exact file was already loaded")
            status = "SKIPPED"

        else:
            # 5. Load the CSV into PostgreSQL
            rows_loaded = load_csv(result.path, batch_id)

            logger.info(
                "Records loaded into raw_data.raw_caiso_hourly: %s",
                rows_loaded
            )

            # 6. Make sure no rows were lost
            if rows_loaded != rows_fetched:
                raise ValueError(
                    f"Row count mismatch: fetched={rows_fetched}, "
                    f"loaded={rows_loaded}"
                )

    except Exception as error:
        status = "FAILED"
        exit_code = 1
        error_message = str(error)
        if http_status is None:
            http_status = get_http_status(error)
        logger.exception("Ingestion failed")

    finally:
        # 7. Record the ingestion attempt in PostgreSQL
        try:
            record_run(
                batch_id,
                started_at,
                status,
                http_status,
                source_file,
                sha256,
                rows_fetched,
                rows_loaded,
                error_message
            )
        except Exception:
            logger.exception("Could not write ingestion log to PostgreSQL")
            if status != "FAILED":
                status = "FAILED"
                exit_code = 1

        # 8. Print the final summary
        elapsed = time.time() - start_time

        logger.info(
            "SUMMARY batch=%s status=%s http=%s fetched=%s "
            "loaded=%s seconds=%.1f",
            batch_id,
            status,
            http_status,
            rows_fetched,
            rows_loaded,
            elapsed
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
