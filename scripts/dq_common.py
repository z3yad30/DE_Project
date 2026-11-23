from dataclasses import dataclass
from typing import Any


class DataQualityError(Exception):
    """Raised when one or more data quality checks fail."""


@dataclass(frozen=True)
class CheckResult:
    rule_name: str
    passed: bool
    offending_count: int | float
    threshold: Any
    message: str

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"