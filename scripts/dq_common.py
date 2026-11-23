import logging
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CheckResult:
    name: str
    tier: str
    status: str
    failed_count: int
    message: str


class DataQualityError(Exception):
    def __init__(
        self,
        failed_results: Iterable[CheckResult] | str,
    ) -> None:
        if isinstance(failed_results, str):
            self.failed_results: list[CheckResult] = []
            message = failed_results
        else:
            self.failed_results = list(failed_results)
            message = "; ".join(
                f"{result.name} (failed_count={result.failed_count})"
                for result in self.failed_results
            )
            if not message:
                message = "Data quality checks failed"

        super().__init__(message)


def log_results(
    results: Iterable[CheckResult],
    logger: logging.Logger,
) -> None:
    for result in results:
        if result.status == "PASS":
            logger.info("DQ PASS [%s]", result.name)
        else:
            logger.error("DQ FAIL [%s]: %s", result.name, result.message)