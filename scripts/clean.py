
import argparse

import pandas as pd

from dataclasses import dataclass, field
from psycopg2.extras import execute_values

from load_raw import connect
from logging_config import get_logger


@dataclass
class CleanStats:
    rows_before: int = 0
    rows_after: int = 0
    exact_duplicates_removed: int = 0
    null_counts_before: dict = field(default_factory=dict)
    null_counts_after: dict = field(default_factory=dict)


logger = get_logger("clean")


def log_stats(stats):
    """Log cleaning counts and null percentages for the report and container logs."""

    logger.info(
        "Rows before/after: %s -> %s; exact duplicates removed: %s",
        stats.rows_before,
        stats.rows_after,
        stats.exact_duplicates_removed,
    )

    for phase, counts in (
        ("before", stats.null_counts_before),
        ("after", stats.null_counts_after),
    ):
        denominator = (
            stats.rows_before if phase == "before" else stats.rows_after
        )
        null_columns = {
            column: count
            for column, count in counts.items()
            if count > 0
        }
        for column, count in null_columns.items():
            percentage = (
                count / denominator * 100 if denominator else 0.0
            )
            logger.info(
                "Null counts %s: %s=%s (%.3f%%)",
                phase,
                column,
                count,
                percentage,
            )


def select_source_batch(conn):
    """Select the latest successful batch that contains raw records."""

    with conn.cursor() as cursor:
        cursor.execute("""
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
            LIMIT 1;
        """)

        result = cursor.fetchone()

    if result is None:
        raise ValueError("No successful ingestion batch found.")

    batch_id = result[0]

    logger.info("Selected source batch: %s", batch_id)

    return batch_id


def read_raw_batch(conn, batch_id):
    """Read all raw records belonging to the selected batch."""

    query = """
        SELECT *
        FROM raw_data.raw_caiso_hourly
        WHERE _batch_id = %s
        ORDER BY datetime_utc;
    """

    with conn.cursor() as cursor:
        cursor.execute(query, (batch_id,))
        column_names = [description.name for description in cursor.description]
        rows = cursor.fetchall()

    df = pd.DataFrame(rows, columns=column_names)

    if df.empty:
        raise ValueError(
            f"No raw records found for batch {batch_id}"
        )

    logger.info(
        "Read %s raw rows from batch %s",
        len(df),
        batch_id
    )

    return df


def clean_dataframe(df):
    """Clean text values and convert columns to their correct data types."""

    df = df.copy()

    # 1. Trim whitespace and convert empty strings to missing values
    text_dtypes = df.select_dtypes(include=["object", "string"]).columns
    for col in text_dtypes:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", pd.NA)

    # 2. Convert datetime columns while preserving timezones
    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"],
        errors="raise",
        utc=True
    )

    # Convert UTC timestamps to California local wall-clock time
    # The source strings include explicit -07:00/-08:00 offsets. Parse them
    # as UTC-aware timestamps first, then convert to California local wall time.
    df["datetime_local"] = (
        pd.to_datetime(
            df["datetime_local"],
            errors="raise",
            utc=True
        )
        .dt.tz_convert("America/Los_Angeles")
        .dt.tz_localize(None)
    )

    if not df.empty:
        local_hour_matches = (
            df["datetime_local"].dt.hour
            == df["hour"].astype("Int64")
        )
        if not local_hour_matches.all():
            mismatch_count = int((~local_hour_matches).sum())
            raise ValueError(
                "datetime_local hour mismatch: "
                f"{mismatch_count} rows differ from the hour column."
            )

        utc_naive = df["datetime_utc"].dt.tz_convert(None)
        offset_hours = (
            (df["datetime_local"] - utc_naive).dt.total_seconds() / 3600
        )
        invalid_offsets = ~offset_hours.isin([-8.0, -7.0])
        if invalid_offsets.any():
            examples = sorted(
                set(offset_hours.loc[invalid_offsets].dropna().tolist())
            )
            raise ValueError(
                "datetime_local UTC offset mismatch; expected -8 or -7 hours, "
                f"found: {examples}"
            )

    df["_ingested_at"] = pd.to_datetime(
        df["_ingested_at"],
        errors="raise",
        utc=True
    )

    # 3. Convert numeric columns
    numeric_cols = [
        "demand_mwh",
        "demand_reported_mwh",
        "demand_imputed_pudl_mwh",
        "temp_c_los_angeles",
        "temp_c_riverside",
        "temp_c_san_diego",
        "temp_c_san_francisco",
        "temp_c_san_jose",
        "temp_c_sacramento",
        "temp_c_fresno",
        "temp_pop_wt_c",
        "temp_pop_wt_f",
        "shortwave_radiation_pop_wt_wm2",
        "cloud_cover_pop_wt_pct",
        "hdh_65",
        "cdh_65",
        "hdd_65_daily",
        "cdd_65_daily",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="raise"
        )

    # 4. Convert integer columns
    integer_cols = [
        "hour",
        "day_of_week",
        "month"
    ]

    for col in integer_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="raise"
        ).astype("Int64")

    # 5. Convert boolean columns with strict validation
    boolean_cols = [
        "demand_is_imputed",
        "temp_is_missing",
        "temp_is_imputed",
        "is_weekend",
        "is_holiday_statutory",
        "is_holiday_observed",
        "is_holiday_ca_statutory",
        "is_holiday_ca_observed",
        "is_dst_transition_day",
        "weather_is_preliminary",
    ]

    for col in boolean_cols:
        normalized = df[col].astype("string")

        invalid_values = (
            df[col].notna()
            & ~normalized.isin(["True", "False"])
        )

        if invalid_values.any():
            examples = (
                df.loc[invalid_values, col]
                .unique()
                .tolist()
            )

            raise ValueError(
                f"Invalid boolean values in {col}: {examples}"
            )

        df[col] = (
            normalized
            .map({
                "True": True,
                "False": False
            })
            .astype("boolean")
        )

    # 6. Validate required demand values
    if df["demand_mwh"].isna().any():
        raise ValueError(
            "demand_mwh contains missing values."
        )

    if (df["demand_mwh"] <= 0).any():
        raise ValueError(
            "demand_mwh contains non-positive values."
        )

    logger.info(
        "Data types converted and required values validated."
    )

    return df


def handle_duplicates(df):
    """Remove exact duplicates and reject conflicting UTC timestamps."""

    df = df.copy()

    rows_before = len(df)

    # 1. Remove exact duplicate rows
    df = df.drop_duplicates().copy()

    exact_duplicates_removed = rows_before - len(df)

    # 2. Check for conflicting records with the same UTC timestamp
    conflicting_timestamps = df[
        df.duplicated(
            subset=["datetime_utc"],
            keep=False
        )
    ]

    if not conflicting_timestamps.empty:
        raise ValueError(
            "Conflicting records found for the same datetime_utc. "
            f"Number of affected rows: {len(conflicting_timestamps)}"
        )

    logger.info(
        "Duplicate check completed. Exact duplicates removed: %s",
        exact_duplicates_removed
    )

    return df, exact_duplicates_removed


def clean_batch(conn):
    """
    Run the complete cleaning process for the latest successful batch.

    Returns:
        tuple: (cleaned DataFrame, CleanStats)
    """

    # 1. Select the latest successful batch
    batch_id = select_source_batch(conn)

    # 2. Read raw data
    df = read_raw_batch(conn, batch_id)

    # 3. Initialize cleaning statistics
    stats = CleanStats()

    stats.rows_before = len(df)
    stats.null_counts_before = df.isna().sum().to_dict()

    # 4. Clean data types and values
    df = clean_dataframe(df)

    # 5. Handle duplicates
    df, duplicates_removed = handle_duplicates(df)

    # 6. Capture final statistics
    stats.rows_after = len(df)
    stats.exact_duplicates_removed = duplicates_removed
    stats.null_counts_after = df.isna().sum().to_dict()

    logger.info(
        "Cleaning completed: %s rows before, %s rows after.",
        stats.rows_before,
        stats.rows_after
    )
    log_stats(stats)

    return df, stats


def load_staging(conn, df):
    """
    Full refresh of clean_data.stg_caiso_clean.

    Creates the staging table if it does not exist,
    truncates previous data, then bulk-inserts the cleaned DataFrame.

    Transaction control is left to the caller.
    """

    columns = [
        "datetime_utc",
        "datetime_local",
        "demand_mwh",
        "demand_reported_mwh",
        "demand_imputed_pudl_mwh",
        "demand_imputed_pudl_mwh_imputation_code",
        "demand_is_imputed",
        "demand_source",
        "temp_c_los_angeles",
        "temp_c_riverside",
        "temp_c_san_diego",
        "temp_c_san_francisco",
        "temp_c_san_jose",
        "temp_c_sacramento",
        "temp_c_fresno",
        "temp_pop_wt_c",
        "temp_pop_wt_f",
        "shortwave_radiation_pop_wt_wm2",
        "cloud_cover_pop_wt_pct",
        "temp_is_missing",
        "temp_is_imputed",
        "hour",
        "day_of_week",
        "month",
        "is_weekend",
        "is_holiday_statutory",
        "is_holiday_observed",
        "is_holiday_ca_statutory",
        "is_holiday_ca_observed",
        "is_dst_transition_day",
        "hdh_65",
        "cdh_65",
        "hdd_65_daily",
        "cdd_65_daily",
        "weather_is_preliminary",
        "_batch_id",
        "_source_file",
    ]

    # Check that all required columns exist
    missing_columns = [
        col for col in columns
        if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required staging columns: {missing_columns}"
        )

    create_table_sql = """
        CREATE SCHEMA IF NOT EXISTS clean_data;

        CREATE TABLE IF NOT EXISTS clean_data.stg_caiso_clean (
            datetime_utc TIMESTAMPTZ PRIMARY KEY,
            datetime_local TIMESTAMP,

            demand_mwh NUMERIC,
            demand_reported_mwh NUMERIC,
            demand_imputed_pudl_mwh NUMERIC,
            demand_imputed_pudl_mwh_imputation_code TEXT,
            demand_is_imputed BOOLEAN,
            demand_source TEXT,

            temp_c_los_angeles NUMERIC,
            temp_c_riverside NUMERIC,
            temp_c_san_diego NUMERIC,
            temp_c_san_francisco NUMERIC,
            temp_c_san_jose NUMERIC,
            temp_c_sacramento NUMERIC,
            temp_c_fresno NUMERIC,

            temp_pop_wt_c NUMERIC,
            temp_pop_wt_f NUMERIC,
            shortwave_radiation_pop_wt_wm2 NUMERIC,
            cloud_cover_pop_wt_pct NUMERIC,

            temp_is_missing BOOLEAN,
            temp_is_imputed BOOLEAN,

            hour SMALLINT,
            day_of_week SMALLINT,
            month SMALLINT,

            is_weekend BOOLEAN,
            is_holiday_statutory BOOLEAN,
            is_holiday_observed BOOLEAN,
            is_holiday_ca_statutory BOOLEAN,
            is_holiday_ca_observed BOOLEAN,
            is_dst_transition_day BOOLEAN,

            hdh_65 NUMERIC,
            cdh_65 NUMERIC,
            hdd_65_daily NUMERIC,
            cdd_65_daily NUMERIC,

            weather_is_preliminary BOOLEAN,

            _batch_id TEXT,
            _source_file TEXT
        );
    """

    with conn.cursor() as cur:
        cur.execute(create_table_sql)

        # Full refresh: remove previous staging rows
        cur.execute(
            "TRUNCATE TABLE clean_data.stg_caiso_clean;"
        )

        # Convert pandas/numpy values to PostgreSQL-compatible values
        rows = []

        for row in df[columns].itertuples(
            index=False,
            name=None
        ):
            clean_row = []

            for value in row:
                if pd.isna(value):
                    clean_row.append(None)

                elif hasattr(value, "to_pydatetime"):
                    clean_row.append(value.to_pydatetime())

                elif hasattr(value, "item"):
                    clean_row.append(value.item())

                else:
                    clean_row.append(value)

            rows.append(tuple(clean_row))

        if rows:
            insert_sql = """
                INSERT INTO clean_data.stg_caiso_clean (
                    datetime_utc,
                    datetime_local,
                    demand_mwh,
                    demand_reported_mwh,
                    demand_imputed_pudl_mwh,
                    demand_imputed_pudl_mwh_imputation_code,
                    demand_is_imputed,
                    demand_source,
                    temp_c_los_angeles,
                    temp_c_riverside,
                    temp_c_san_diego,
                    temp_c_san_francisco,
                    temp_c_san_jose,
                    temp_c_sacramento,
                    temp_c_fresno,
                    temp_pop_wt_c,
                    temp_pop_wt_f,
                    shortwave_radiation_pop_wt_wm2,
                    cloud_cover_pop_wt_pct,
                    temp_is_missing,
                    temp_is_imputed,
                    hour,
                    day_of_week,
                    month,
                    is_weekend,
                    is_holiday_statutory,
                    is_holiday_observed,
                    is_holiday_ca_statutory,
                    is_holiday_ca_observed,
                    is_dst_transition_day,
                    hdh_65,
                    cdh_65,
                    hdd_65_daily,
                    cdd_65_daily,
                    weather_is_preliminary,
                    _batch_id,
                    _source_file
                )
                VALUES %s
            """

            execute_values(
                cur,
                insert_sql,
                rows,
                page_size=1000
            )

    logger.info(
        "Loaded %s rows into clean_data.stg_caiso_clean",
        len(rows)
    )

    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean the latest successful CAISO ingestion batch."
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Load the cleaned frame into staging and commit the transaction.",
    )
    args = parser.parse_args()

    conn = None

    try:
        conn = connect()

        df, stats = clean_batch(conn)

        if args.load:
            loaded_rows = load_staging(conn, df)
            conn.commit()
            logger.info(
                "Committed staging load with %s rows",
                loaded_rows,
            )

        print("\n========== CLEANING SUMMARY ==========")
        print(f"Rows before cleaning: {stats.rows_before}")
        print(f"Rows after cleaning: {stats.rows_after}")
        print(
            "Exact duplicates removed: "
            f"{stats.exact_duplicates_removed}"
        )

        print("\n========== NULL COUNTS BEFORE ==========")

        for column, count in stats.null_counts_before.items():
            percentage = (
                count / stats.rows_before * 100
                if stats.rows_before else 0
            )

            print(
                f"{column}: {count:,} ({percentage:.3f}%)"
            )

        print("\n========== NULL COUNTS AFTER ==========")

        for column, count in stats.null_counts_after.items():
            percentage = (
                count / stats.rows_after * 100
                if stats.rows_after else 0
            )

            print(
                f"{column}: {count:,} ({percentage:.3f}%)"
            )

        print("\nCleaning completed successfully.")

    except Exception:
        logger.exception("Cleaning failed")
        raise

    finally:
        if conn is not None:
            conn.close()
