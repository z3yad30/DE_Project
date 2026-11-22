import argparse
import logging
import sys

from clean import clean_batch
from dq_common import DataQualityError
from load_raw import connect
from preload_checks import run_preload_checks


logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Demonstrate preload checks against the latest real clean batch"
    )
    parser.add_argument(
        "--case",
        required=True,
        choices=["negative_demand", "duplicate_ts", "missing_column"],
    )
    args = parser.parse_args()

    connection = connect()
    try:
        connection.set_session(readonly=True)
        clean_df, stats = clean_batch(connection)
    finally:
        connection.close()

    df = clean_df.copy(deep=True)
    if args.case == "negative_demand":
        column_index = df.columns.get_loc("demand_mwh")
        df.iat[0, column_index] = -1
    elif args.case == "duplicate_ts":
        if len(df) < 2:
            raise DataQualityError(
                "Cannot demonstrate duplicate_ts with fewer than two clean rows"
            )
        timestamp_index = df.columns.get_loc("datetime_utc")
        df.iat[1, timestamp_index] = df.iat[0, timestamp_index]
    else:
        df = df.drop(columns=["demand_reported_mwh"])

    batch_id = df["_batch_id"].iloc[0] if not df.empty else "unknown"
    print(f"PRELOAD DEMO case={args.case} batch={batch_id}")
    try:
        run_preload_checks(df, expected_raw_rows=stats.rows_before)
    except DataQualityError as exc:
        logger.error("Preload checks rejected case '%s': %s", args.case, exc)
        return 1

    logger.error("Injected defect was not detected for case '%s'", args.case)
    return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    sys.exit(main())
