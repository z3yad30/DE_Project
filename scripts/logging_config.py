
import logging
import sys
from datetime import datetime, timezone


class UTCFormatter(logging.Formatter):

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc
        )

        if datefmt:
            return dt.strftime(datefmt)

        return dt.isoformat()


def add_stdout_handler(target_logger):

    for handler in target_logger.handlers:
        if (
            isinstance(handler, logging.StreamHandler)
            and handler.stream is sys.stdout
        ):
            return

    handler = logging.StreamHandler(sys.stdout)

    formatter = UTCFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handler.setFormatter(formatter)
    target_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:

    # Configure the root logger so other modules
    # can send their messages to the same output
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    add_stdout_handler(root_logger)

    # Configure the requested module logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    add_stdout_handler(logger)

    # Prevent duplicate messages from reaching root
    logger.propagate = False

    return logger
