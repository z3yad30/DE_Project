-- Proves how many source rows are currently stored across all batches.
SELECT count(*)
FROM raw_data.raw_caiso_hourly;

-- Shows ten stored records in chronological order using the source timestamp column.
SELECT *
FROM raw_data.raw_caiso_hourly
ORDER BY datetime_utc
LIMIT 10;

-- Proves which batches contributed rows and how many rows each appended.
SELECT _batch_id, count(*) AS rows_loaded
FROM raw_data.raw_caiso_hourly
GROUP BY _batch_id
ORDER BY _batch_id;

-- Shows the five most recently recorded ingestion runs and their outcomes.
SELECT *
FROM raw_data.ingestion_log
ORDER BY finished_at DESC
LIMIT 5;

-- Lists the raw table's columns and database types in their defined order.
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'raw_data'
  AND table_name = 'raw_caiso_hourly'
ORDER BY ordinal_position;
