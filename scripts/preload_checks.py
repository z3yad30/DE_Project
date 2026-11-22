import logging
import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from dq_common import DataQualityError  # type: ignore
except ImportError:
    class DataQualityError(Exception):
        """Raised when one or more data quality checks fail."""


@dataclass
class CheckResult:
    rule_name: str
    passed: bool
    offending_count: int
    threshold: Any
    message: str


THRESHOLDS: dict[str, Any] = {
    "expected_row_diff_max": 0,
    "datetime_utc_null_max": 0,
    "datetime_utc_duplicate_max": 0,
    "demand_mwh_null_max": 0,
    "demand_mwh_non_positive_max": 0,
    "null_pct_max": {
        "demand_reported_mwh": 1.0,
        "demand_imputed_pudl_mwh": 2.0,
        "hdd_65_daily": 0.1,
        "cdd_65_daily": 0.1,
    },
    "cloud_cover_min": 0.0,
    "cloud_cover_max": 100.0,
    "non_negative_min": 0.0,
    "hour_min": 0,
    "hour_max": 23,
    "month_min": 1,
    "month_max": 12,
    "day_of_week_min": 0,
    "day_of_week_max": 6,
}

REQUIRED_COLUMNS: list[str] = [
    "datetime_utc",
    "demand_mwh",
]

NON_NEGATIVE_COLUMNS: list[str] = [
    "shortwave_radiation_pop_wt_wm2",
    "hdh_65",
    "cdh_65",
    "hdd_65_daily",
    "cdd_65_daily",
]


def _check_columns_present(df: pd.DataFrame) -> CheckResult:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    passed = len(missing) == 0
    msg = (
        "All required columns present"
        if passed
        else f"Missing required columns: {missing}"
    )
    return CheckResult("required_columns_present", passed, len(missing), REQUIRED_COLUMNS, msg)


def _check_row_count(df: pd.DataFrame, expected_raw_rows: int | None) -> CheckResult:
    actual = len(df)
    if expected_raw_rows is None:
        return CheckResult(
            "row_count_match",
            True,
            0,
            "raw_batch_rows - removals",
            f"Row count={actual} (no expected_raw_rows provided)",
        )
    diff = abs(actual - expected_raw_rows)
    max_diff = THRESHOLDS["expected_row_diff_max"]
    passed = diff <= max_diff
    msg = (
        f"expected {expected_raw_rows}, found {actual} (diff={diff})"
        if not passed
        else f"Rows match expected={actual}"
    )
    return CheckResult("row_count_match", passed, diff, max_diff, msg)


def _check_datetime_utc(df: pd.DataFrame) -> list[CheckResult]:
    results: list[CheckResult] = []
    if "datetime_utc" not in df.columns:
        return results

    null_cnt = int(df["datetime_utc"].isna().sum())
    max_null = THRESHOLDS["datetime_utc_null_max"]
    results.append(
        CheckResult(
            "datetime_utc_not_null",
            null_cnt <= max_null,
            null_cnt,
            max_null,
            f"expected <={max_null} nulls, found {null_cnt}",
        )
    )

    dup_cnt = int(df["datetime_utc"].dropna().duplicated().sum())
    max_dup = THRESHOLDS["datetime_utc_duplicate_max"]
    results.append(
        CheckResult(
            "datetime_utc_unique",
            dup_cnt <= max_dup,
            dup_cnt,
            max_dup,
            f"expected <={max_dup} duplicates, found {dup_cnt}",
        )
    )
    return results


def _check_demand_mwh(df: pd.DataFrame) -> list[CheckResult]:
    results: list[CheckResult] = []
    if "demand_mwh" not in df.columns:
        return results

    s = pd.to_numeric(df["demand_mwh"], errors="coerce")
    null_cnt = int(s.isna().sum())
    max_null = THRESHOLDS["demand_mwh_null_max"]
    results.append(
        CheckResult(
            "demand_mwh_not_null",
            null_cnt <= max_null,
            null_cnt,
            max_null,
            f"expected <={max_null} nulls/unparseable, found {null_cnt}",
        )
    )

    non_pos_cnt = int((s.dropna() <= 0).sum())
    max_non_pos = THRESHOLDS["demand_mwh_non_positive_max"]
    results.append(
        CheckResult(
            "demand_mwh_positive",
            non_pos_cnt <= max_non_pos,
            non_pos_cnt,
            max_non_pos,
            f"expected <={max_non_pos} values <= 0, found {non_pos_cnt}",
        )
    )
    return results


def _check_null_thresholds(df: pd.DataFrame) -> list[CheckResult]:
    results: list[CheckResult] = []
    total_rows = len(df)
    if total_rows == 0:
        return results

    for col, max_pct in THRESHOLDS["null_pct_max"].items():
        if col not in df.columns:
            continue
        null_cnt = int(df[col].isna().sum())
        pct = (null_cnt / total_rows) * 100.0
        passed = pct <= max_pct
        msg = f"{col} null={pct:.3f}% ({null_cnt}/{total_rows}), max={max_pct}%"
        results.append(CheckResult(f"null_pct_{col}", passed, null_cnt, max_pct, msg))
    return results


def _check_ranges(df: pd.DataFrame) -> list[CheckResult]:
    results: list[CheckResult] = []

    if "cloud_cover_pop_wt_pct" in df.columns:
        s = pd.to_numeric(df["cloud_cover_pop_wt_pct"], errors="coerce").dropna()
        lo, hi = THRESHOLDS["cloud_cover_min"], THRESHOLDS["cloud_cover_max"]
        bad = int(((s < lo) | (s > hi)).sum())
        results.append(
            CheckResult(
                "range_cloud_cover_pct",
                bad == 0,
                bad,
                f"[{lo}, {hi}]",
                f"expected in [{lo}, {hi}], found {bad} out-of-range",
            )
        )

    for col in NON_NEGATIVE_COLUMNS:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            lo = THRESHOLDS["non_negative_min"]
            bad = int((s < lo).sum())
            results.append(
                CheckResult(
                    f"range_{col}_non_negative",
                    bad == 0,
                    bad,
                    f">={lo}",
                    f"expected >={lo}, found {bad} negative values",
                )
            )

    range_specs = [
        ("hour", "hour_min", "hour_max"),
        ("month", "month_min", "month_max"),
        ("day_of_week", "day_of_week_min", "day_of_week_max"),
    ]
    for col, k_min, k_max in range_specs:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            lo, hi = THRESHOLDS[k_min], THRESHOLDS[k_max]
            bad = int(((s < lo) | (s > hi)).sum())
            results.append(
                CheckResult(
                    f"range_{col}",
                    bad == 0,
                    bad,
                    f"[{lo}, {hi}]",
                    f"expected in [{lo}, {hi}], found {bad} out-of-range",
                )
            )

    return results


def run_preload_checks(
    df: pd.DataFrame,
    expected_raw_rows: int | None = None,
) -> list[CheckResult]:
    if not isinstance(df, pd.DataFrame):
        raise DataQualityError("Pre-load check input must be a pandas DataFrame")

    all_results: list[CheckResult] = []
    all_results.append(_check_columns_present(df))
    all_results.append(_check_row_count(df, expected_raw_rows))
    all_results.extend(_check_datetime_utc(df))
    all_results.extend(_check_demand_mwh(df))
    all_results.extend(_check_null_thresholds(df))
    all_results.extend(_check_ranges(df))

    failures: list[CheckResult] = []
    for res in all_results:
        if res.passed:
            logger.info("DQ PASS [%s]: %s", res.rule_name, res.message)
        else:
            logger.error("DQ FAIL [%s]: %s", res.rule_name, res.message)
            failures.append(res)

    if failures:
        summary = "; ".join(f"[{f.rule_name}] {f.message}" for f in failures)
        raise DataQualityError(f"Pre-load checks failed ({len(failures)}): {summary}")

    return all_results
