from typing import Any
import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_dtype,
    is_datetime64tz_dtype,
    is_integer_dtype,
    is_numeric_dtype,
    is_object_dtype,
    is_string_dtype,
)

from dq_common import CheckResult, DataQualityError, log_results
from logging_config import get_logger


logger = get_logger("preload_checks")

THRESHOLDS: dict[str, Any] = {
    "documented_removals": 0,
    "row_count_difference_max": 0,
    "datetime_utc_null_max": 0,
    "datetime_utc_duplicate_rows_max": 0,
    "demand_mwh_invalid_max": 0,
    "null_pct_max": {
        "demand_reported_mwh": 1.0,
        "demand_imputed_pudl_mwh": 2.0,
        "hdd_65_daily": 0.1,
        "cdd_65_daily": 0.1,
    },
    "cloud_cover_min": 0,
    "cloud_cover_max": 100,
    "non_negative_min": 0,
    "hour_min": 0,
    "hour_max": 23,
    "month_min": 1,
    "month_max": 12,
    "day_of_week_min": 0,
    "day_of_week_max": 6,
}

STAGING_COLUMNS = [
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

EXPECTED_DTYPES = {
    "datetime_utc": "utc_datetime",
    "datetime_local": "naive_datetime",
    "demand_mwh": "numeric",
    "demand_reported_mwh": "numeric",
    "demand_imputed_pudl_mwh": "numeric",
    "demand_imputed_pudl_mwh_imputation_code": "text",
    "demand_is_imputed": "boolean",
    "demand_source": "text",
    "temp_c_los_angeles": "numeric",
    "temp_c_riverside": "numeric",
    "temp_c_san_diego": "numeric",
    "temp_c_san_francisco": "numeric",
    "temp_c_san_jose": "numeric",
    "temp_c_sacramento": "numeric",
    "temp_c_fresno": "numeric",
    "temp_pop_wt_c": "numeric",
    "temp_pop_wt_f": "numeric",
    "shortwave_radiation_pop_wt_wm2": "numeric",
    "cloud_cover_pop_wt_pct": "numeric",
    "temp_is_missing": "boolean",
    "temp_is_imputed": "boolean",
    "hour": "integer",
    "day_of_week": "integer",
    "month": "integer",
    "is_weekend": "boolean",
    "is_holiday_statutory": "boolean",
    "is_holiday_observed": "boolean",
    "is_holiday_ca_statutory": "boolean",
    "is_holiday_ca_observed": "boolean",
    "is_dst_transition_day": "boolean",
    "hdh_65": "numeric",
    "cdh_65": "numeric",
    "hdd_65_daily": "numeric",
    "cdd_65_daily": "numeric",
    "weather_is_preliminary": "boolean",
    "_batch_id": "text",
    "_source_file": "text",
}




def _result(
    rule_name: str,
    offending_count: int,
    threshold: Any,
    message: str,
) -> CheckResult:
    return CheckResult(
        name=rule_name,
        tier="pre-load",
        status="PASS" if offending_count <= threshold else "FAIL",
        failed_count=(
            offending_count if offending_count > threshold else 0
        ),
        message=message,
    )


def _check_required_columns(df: pd.DataFrame) -> CheckResult:
    missing = [column for column in STAGING_COLUMNS if column not in df]
    return _result(
        "required_columns",
        len(missing),
        0,
        f"missing columns: {missing}" if missing else "all staging columns present",
    )


def _dtype_matches(series: pd.Series, expected: str) -> bool:
    dtype = series.dtype
    if expected == "utc_datetime":
        return is_datetime64tz_dtype(dtype) and str(series.dt.tz) == "UTC"
    if expected == "naive_datetime":
        return is_datetime64_dtype(dtype) and not is_datetime64tz_dtype(dtype)
    if expected == "numeric":
        return is_numeric_dtype(dtype) and not is_bool_dtype(dtype)
    if expected == "integer":
        return is_integer_dtype(dtype)
    if expected == "boolean":
        return is_bool_dtype(dtype)
    if expected == "text":
        return (
            (is_string_dtype(dtype) or is_object_dtype(dtype))
            and series.map(
                lambda value: isinstance(value, str) or pd.isna(value)
            )
            .all()
        )
    raise ValueError(f"Unknown expected dtype category: {expected}")


def _check_expected_dtypes(df: pd.DataFrame) -> CheckResult:
    mismatches = []
    for column, expected in EXPECTED_DTYPES.items():
        if column not in df:
            mismatches.append(f"{column}=missing (expected {expected})")
        elif not _dtype_matches(df[column], expected):
            mismatches.append(
                f"{column}={df[column].dtype} (expected {expected})"
            )
    return _result(
        "expected_dtypes",
        len(mismatches),
        0,
        (
            f"unexpected dtypes: {mismatches}"
            if mismatches
            else "all staging dtypes match"
        ),
    )


def _check_row_count(
    df: pd.DataFrame,
    expected_raw_rows: int,
) -> CheckResult:
    expected_rows = expected_raw_rows - THRESHOLDS["documented_removals"]
    difference = abs(len(df) - expected_rows)
    return _result(
        "row_count",
        difference,
        THRESHOLDS["row_count_difference_max"],
        f"expected {expected_rows} rows, found {len(df)}",
    )


def _check_datetime_utc_not_null(df: pd.DataFrame) -> CheckResult:
    if "datetime_utc" not in df:
        return _result(
            "datetime_utc_not_null", 1, THRESHOLDS["datetime_utc_null_max"],
            "datetime_utc column is missing",
        )
    null_count = int(df["datetime_utc"].isna().sum())
    return _result(
        "datetime_utc_not_null",
        null_count,
        THRESHOLDS["datetime_utc_null_max"],
        f"{null_count} NULL values",
    )


def _check_datetime_utc_unique(df: pd.DataFrame) -> CheckResult:
    if "datetime_utc" not in df:
        return _result(
            "datetime_utc_unique",
            1,
            THRESHOLDS["datetime_utc_duplicate_rows_max"],
            "datetime_utc column is missing",
        )
    duplicate_rows = int(
        df.loc[df["datetime_utc"].notna(), "datetime_utc"]
        .duplicated(keep=False)
        .sum()
    )
    return _result(
        "datetime_utc_unique",
        duplicate_rows,
        THRESHOLDS["datetime_utc_duplicate_rows_max"],
        f"{duplicate_rows} rows have duplicate timestamps",
    )


def _check_demand_mwh(df: pd.DataFrame) -> CheckResult:
    if "demand_mwh" not in df:
        return _result(
            "demand_mwh_positive",
            1,
            THRESHOLDS["demand_mwh_invalid_max"],
            "demand_mwh column is missing",
        )
    demand = pd.to_numeric(df["demand_mwh"], errors="coerce")
    invalid_count = int((demand.isna() | (demand <= 0)).sum())
    return _result(
        "demand_mwh_positive",
        invalid_count,
        THRESHOLDS["demand_mwh_invalid_max"],
        f"{invalid_count} NULL or non-positive values",
    )


def _check_null_share(df: pd.DataFrame, column: str) -> CheckResult:
    threshold = THRESHOLDS["null_pct_max"][column]
    if column not in df:
        return CheckResult(
            name=f"{column}_null_share",
            tier="pre-load",
            status="FAIL",
            failed_count=1,
            message=f"{column} column is missing",
        )
    null_count = int(df[column].isna().sum())
    null_pct = null_count / len(df) * 100 if len(df) else 0.0
    passed = null_pct <= threshold
    return CheckResult(
        name=f"{column}_null_share",
        tier="pre-load",
        status="PASS" if passed else "FAIL",
        failed_count=0 if passed else null_count,
        message=(
            f"{null_pct:.3f}% NULL ({null_count} rows; "
            f"maximum {threshold:.3f}%)"
        ),
    )


def _check_demand_reported_null_share(df: pd.DataFrame) -> CheckResult:
    return _check_null_share(df, "demand_reported_mwh")


def _check_demand_imputed_null_share(df: pd.DataFrame) -> CheckResult:
    return _check_null_share(df, "demand_imputed_pudl_mwh")


def _check_hdd_daily_null_share(df: pd.DataFrame) -> CheckResult:
    return _check_null_share(df, "hdd_65_daily")


def _check_cdd_daily_null_share(df: pd.DataFrame) -> CheckResult:
    return _check_null_share(df, "cdd_65_daily")


def _check_range(
    df: pd.DataFrame,
    column: str,
    minimum: int | float,
    maximum: int | float | None = None,
) -> CheckResult:
    rule_name = f"{column}_range"
    if column not in df:
        return _result(rule_name, 1, 0, f"{column} column is missing")

    values = pd.to_numeric(df[column], errors="coerce")
    invalid = values.isna() & df[column].notna()
    outside = values < minimum
    if maximum is not None:
        outside |= values > maximum
    offending_count = int((invalid | outside).sum())
    expected = (
        f"{minimum} <= values <= {maximum}"
        if maximum is not None
        else f"values >= {minimum}"
    )
    return _result(
        rule_name,
        offending_count,
        0,
        f"expected {expected}; {offending_count} out-of-range values",
    )


def _check_cloud_cover_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(
        df,
        "cloud_cover_pop_wt_pct",
        THRESHOLDS["cloud_cover_min"],
        THRESHOLDS["cloud_cover_max"],
    )


def _check_shortwave_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(
        df, "shortwave_radiation_pop_wt_wm2", THRESHOLDS["non_negative_min"]
    )


def _check_hdh_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(df, "hdh_65", THRESHOLDS["non_negative_min"])


def _check_cdh_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(df, "cdh_65", THRESHOLDS["non_negative_min"])


def _check_hdd_daily_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(df, "hdd_65_daily", THRESHOLDS["non_negative_min"])


def _check_cdd_daily_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(df, "cdd_65_daily", THRESHOLDS["non_negative_min"])


def _check_hour_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(
        df, "hour", THRESHOLDS["hour_min"], THRESHOLDS["hour_max"]
    )


def _check_month_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(
        df, "month", THRESHOLDS["month_min"], THRESHOLDS["month_max"]
    )


def _check_day_of_week_range(df: pd.DataFrame) -> CheckResult:
    return _check_range(
        df,
        "day_of_week",
        THRESHOLDS["day_of_week_min"],
        THRESHOLDS["day_of_week_max"],
    )


def run_preload_checks(
    df: pd.DataFrame,
    expected_raw_rows: int,
) -> list[CheckResult]:
    if not isinstance(df, pd.DataFrame):
        raise DataQualityError("Pre-load check input must be a pandas DataFrame")

    results = [
        _check_required_columns(df),
        _check_expected_dtypes(df),
        _check_row_count(df, expected_raw_rows),
        _check_datetime_utc_not_null(df),
        _check_datetime_utc_unique(df),
        _check_demand_mwh(df),
        _check_demand_reported_null_share(df),
        _check_demand_imputed_null_share(df),
        _check_hdd_daily_null_share(df),
        _check_cdd_daily_null_share(df),
        _check_cloud_cover_range(df),
        _check_shortwave_range(df),
        _check_hdh_range(df),
        _check_cdh_range(df),
        _check_hdd_daily_range(df),
        _check_cdd_daily_range(df),
        _check_hour_range(df),
        _check_month_range(df),
        _check_day_of_week_range(df),
    ]

    log_results(results, logger)
    failures = [result for result in results if result.status == "FAIL"]

    if failures:
        raise DataQualityError(failures)
    return results
