import csv
import logging
import os
import sys
import time
from pathlib import Path

import psycopg2
from psycopg2 import sql


logger = logging.getLogger("load_raw")


def connect():
    max_retries = int(os.getenv("MAX_RETRIES", "3"))
    if max_retries < 1:
        raise ValueError("MAX_RETRIES must be at least 1")

    connection_params = {
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ["POSTGRES_PORT"]),
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "dbname": os.environ["POSTGRES_DB"],
    }

    for attempt in range(1, max_retries + 1):
        try:
            connection = psycopg2.connect(**connection_params)
            logger.info("Connected to PostgreSQL")
            return connection
        except psycopg2.Error as exc:
            logger.warning(
                "PostgreSQL connection attempt %s/%s failed: %s",
                attempt,
                max_retries,
                exc,
            )
            if attempt == max_retries:
                raise
            time.sleep(2**attempt)


def ensure_schema() -> None:
    schema_path = Path(__file__).resolve().parent.parent / "sql" / "01_raw_schema.sql"
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(schema_path.read_text(encoding="utf-8"))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def already_loaded(sha256: str) -> bool:
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM raw_data.ingestion_log
                    WHERE sha256 = %s AND status = 'SUCCESS'
                )
                """,
                (sha256,),
            )
            return cursor.fetchone()[0]
    finally:
        connection.close()


def load_csv(csv_path: str, batch_id: str) -> int:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        header = next(csv.reader(csv_file), None)
    if header is None:
        raise ValueError("CSV file is empty and has no header")

    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                  AND column_name NOT IN (%s, %s, %s)
                ORDER BY ordinal_position
                """,
                (
                    "raw_data",
                    "raw_caiso_hourly",
                    "_batch_id",
                    "_source_file",
                    "_ingested_at",
                ),
            )
            table_columns = [row[0] for row in cursor.fetchall()]

            if header != table_columns:
                missing = [column for column in table_columns if column not in header]
                extra = [column for column in header if column not in table_columns]
                details = [
                    f"missing columns: {missing}",
                    f"extra columns: {extra}",
                ]
                if not missing and not extra:
                    details.append("column order differs")
                raise ValueError(
                    "CSV header does not match raw_data.raw_caiso_hourly: "
                    + "; ".join(details)
                )

            logger.info("CSV header check passed for %s", path.name)

            data_identifiers = [sql.Identifier(column) for column in header]
            column_definitions = sql.SQL(", ").join(
                identifier + sql.SQL(" TEXT")
                for identifier in data_identifiers
            )
            temp_table = sql.Identifier("_raw_caiso_hourly_load")
            cursor.execute(
                sql.SQL("CREATE TEMP TABLE {} ({})").format(
                    temp_table,
                    column_definitions,
                )
            )

            copy_query = sql.SQL(
                "COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)"
            ).format(temp_table, sql.SQL(", ").join(data_identifiers))
            with path.open("r", encoding="utf-8", newline="") as csv_file:
                cursor.copy_expert(copy_query.as_string(connection), csv_file)

            insert_columns = data_identifiers + [
                sql.Identifier("_batch_id"),
                sql.Identifier("_source_file"),
            ]
            select_columns = sql.SQL(", ").join(data_identifiers)
            insert_query = sql.SQL(
                "INSERT INTO {} ({}) SELECT {}, %s, %s FROM {}"
            ).format(
                sql.Identifier("raw_data", "raw_caiso_hourly"),
                sql.SQL(", ").join(insert_columns),
                select_columns,
                temp_table,
            )
            cursor.execute(insert_query, (batch_id, path.name))
            rows_loaded = cursor.rowcount

        connection.commit()
        logger.info("Loaded %s rows from %s", rows_loaded, path.name)
        return rows_loaded
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def record_run(
    batch_id,
    started_at,
    status,
    http_status,
    source_file,
    sha256,
    rows_fetched,
    rows_loaded,
    error,
) -> None:
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO raw_data.ingestion_log (
                    batch_id,
                    started_at,
                    finished_at,
                    source,
                    http_status,
                    source_file,
                    sha256,
                    rows_fetched,
                    rows_loaded,
                    status,
                    error
                )
                VALUES (%s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    batch_id,
                    started_at,
                    "Kaggle",
                    http_status,
                    source_file,
                    sha256,
                    rows_fetched,
                    rows_loaded,
                    status,
                    error,
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    csv_path = sys.argv[1]
    ensure_schema()
    print(load_csv(csv_path, "manual-test"))
