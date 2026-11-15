
import os
import time
import hashlib
import logging
import tempfile
import zipfile
import shutil

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests


logger = logging.getLogger(__name__)


@dataclass
class SourceResult:
    path: str
    http_status: int
    sha256: str
    size_bytes: int


def fetch_source(raw_dir: str) -> SourceResult:
    """
    Download the CAISO dataset from Kaggle,
    extract the original CSV, and return its metadata.
    """

    # Read configuration from environment variables
    kaggle_username = os.getenv("KAGGLE_USERNAME")
    kaggle_key = os.getenv("KAGGLE_KEY")

    dataset = os.getenv(
        "KAGGLE_DATASET",
        "arimancy/caiso-hourly-demand-weather"
    )

    max_retries = int(os.getenv("MAX_RETRIES", "3"))

    if max_retries < 1:
        raise ValueError("MAX_RETRIES must be at least 1")

    # Validate Kaggle credentials
    if not kaggle_username or not kaggle_key:
        raise ValueError(
            "Missing Kaggle credentials. "
            "Set KAGGLE_USERNAME and KAGGLE_KEY in your environment."
        )

    # Prepare download URL
    url = f"https://www.kaggle.com/api/v1/datasets/download/{dataset}"

    logger.info("Starting Kaggle dataset extraction")
    logger.info("Dataset: %s", dataset)
    logger.info("Request URL: %s", url)

    response = None

    # Retry download if a temporary error occurs
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Downloading dataset (attempt %s/%s)",
                attempt,
                max_retries
            )

            response = requests.get(
                url,
                auth=(kaggle_username, kaggle_key),
                stream=True,
                timeout=(10, 300)
            )

            logger.info(
                "Kaggle HTTP status: %s",
                response.status_code
            )

            response.raise_for_status()
            break

        except requests.exceptions.HTTPError as exc:
            status = response.status_code
            response.close()

            # Authentication and dataset errors are not retryable
            if status == 401:
                raise RuntimeError(
                    "Kaggle rejected credentials (401). "
                    "Check KAGGLE_USERNAME / KAGGLE_KEY"
                ) from exc

            if status == 403:
                raise RuntimeError(
                    "Kaggle access forbidden (403). "
                    "Check your dataset access permissions."
                ) from exc

            if status == 404:
                raise RuntimeError(
                    "Kaggle dataset not found (404). "
                    "Check KAGGLE_DATASET."
                ) from exc

            # Retry only server errors (5xx)
            if status < 500 or attempt == max_retries:
                raise

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout
        ):
            if attempt == max_retries:
                raise

        wait_seconds = 2 ** attempt

        logger.warning(
            "Download failed. Retrying in %s seconds...",
            wait_seconds
        )

        time.sleep(wait_seconds)

    # Prepare raw data directory
    raw_path = Path(raw_dir)
    raw_path.mkdir(parents=True, exist_ok=True)

    temp_zip_path = None

    try:
        # Download ZIP file to a temporary location
        with tempfile.NamedTemporaryFile(
            suffix=".zip",
            delete=False
        ) as temp_zip:

            temp_zip_path = Path(temp_zip.name)

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    temp_zip.write(chunk)

        http_status = response.status_code
        response.close()

        logger.info("Dataset ZIP downloaded successfully")

        try:
            # Find the CSV file inside the ZIP
            with zipfile.ZipFile(temp_zip_path, "r") as archive:

                csv_files = [
                    name for name in archive.namelist()
                    if name.lower().endswith(".csv")
                ]

                if len(csv_files) != 1:
                    raise ValueError(
                        f"Expected exactly one CSV file, "
                        f"found {len(csv_files)}"
                    )

                csv_name = csv_files[0]

                # Create timestamped output filename
                timestamp = datetime.now(timezone.utc).strftime(
                    "%Y%m%dT%H%M%SZ"
                )

                output_path = (
                    raw_path / f"caiso_hourly_{timestamp}.csv"
                )

                # Extract CSV without modifying its contents
                with archive.open(csv_name, "r") as source:
                    with output_path.open("wb") as destination:
                        shutil.copyfileobj(source, destination)

        except zipfile.BadZipFile as exc:
            raise RuntimeError(
                "Response was not a ZIP file; "
                "check credentials/dataset slug"
            ) from exc

        logger.info(
            "CSV extracted successfully: %s",
            output_path
        )

        # Calculate SHA-256 checksum
        sha256_hash = hashlib.sha256()

        with output_path.open("rb") as file:
            for chunk in iter(
                lambda: file.read(1024 * 1024),
                b""
            ):
                sha256_hash.update(chunk)

        sha256_value = sha256_hash.hexdigest()

        # Get file size
        size_bytes = output_path.stat().st_size

        logger.info("SHA-256: %s", sha256_value)
        logger.info("File size: %s bytes", size_bytes)

        # Return extraction metadata
        return SourceResult(
            path=str(output_path),
            http_status=http_status,
            sha256=sha256_value,
            size_bytes=size_bytes
        )

    finally:
        # Close response if it is still open
        if response is not None:
            response.close()

        # Remove temporary ZIP file
        if temp_zip_path is not None:
            temp_zip_path.unlink(missing_ok=True)


if __name__ == "__main__":

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        )
    )

    raw_dir = os.environ["RAW_DIR"]

    result = fetch_source(raw_dir)

    print("Extraction completed successfully!")
    print("File path:", result.path)
    print("HTTP status:", result.http_status)
    print("SHA-256:", result.sha256)
    print("File size:", result.size_bytes, "bytes")
