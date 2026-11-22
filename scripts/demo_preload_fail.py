import argparse
import logging
import sys

import pandas as pd

from preload_checks import DataQualityError, run_preload_checks

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _sample_clean_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime_utc": pd.to_datetime(
                ["2024-01-01 00:00:00+00:00", "2024-01-01 01:00:00+00:00"],
                utc=True,
            ),
            "demand_mwh": [25000.0, 26000.0],
            "demand_reported_mwh": [25000.0, 26000.0],
            "demand_imputed_pudl_mwh": [25000.0, 26000.0],
            "hdd_65_daily": [10.0, 10.0],
            "cdd_65_daily": [0.0, 0.0],
            "cloud_cover_pop_wt_pct": [20.0, 35.0],
            "shortwave_radiation_pop_wt_wm2": [0.0, 120.0],
            "hdh_65": [10.0, 9.0],
            "cdh_65": [0.0, 0.0],
            "hour": [0, 1],
            "month": [1, 1],
            "day_of_week": [0, 0],
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo pre-load data quality failures")
    parser.add_argument(
        "--case",
        required=True,
        choices=["negative_demand", "duplicate_ts", "missing_column"],
    )
    args = parser.parse_args()

    df = _sample_clean_df().copy()
    expected_rows = len(df)

    if args.case == "negative_demand":
        df.loc[0, "demand_mwh"] = -150.0
    elif args.case == "duplicate_ts":
        df.loc[1, "datetime_utc"] = df.loc[0, "datetime_utc"]
    elif args.case == "missing_column":
        df = df.drop(columns=["demand_mwh"])

    try:
        run_preload_checks(df, expected_raw_rows=expected_rows)
    except DataQualityError as exc:
        logging.error("Pipeline halted: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
