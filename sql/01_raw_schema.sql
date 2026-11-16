CREATE SCHEMA IF NOT EXISTS raw_data;

-- Stores each source CSV row unchanged; TEXT preserves the source values without type interpretation.
CREATE TABLE IF NOT EXISTS raw_data.raw_caiso_hourly (
    datetime_utc TEXT,
    datetime_local TEXT,
    demand_mwh TEXT,
    demand_reported_mwh TEXT,
    demand_imputed_pudl_mwh TEXT,
    demand_imputed_pudl_mwh_imputation_code TEXT,
    demand_is_imputed TEXT,
    demand_source TEXT,
    temp_c_los_angeles TEXT,
    temp_c_riverside TEXT,
    temp_c_san_diego TEXT,
    temp_c_san_francisco TEXT,
    temp_c_san_jose TEXT,
    temp_c_sacramento TEXT,
    temp_c_fresno TEXT,
    temp_pop_wt_c TEXT,
    temp_pop_wt_f TEXT,
    shortwave_radiation_pop_wt_wm2 TEXT,
    cloud_cover_pop_wt_pct TEXT,
    temp_is_missing TEXT,
    temp_is_imputed TEXT,
    hour TEXT,
    day_of_week TEXT,
    month TEXT,
    is_weekend TEXT,
    is_holiday_statutory TEXT,
    is_holiday_observed TEXT,
    is_holiday_ca_statutory TEXT,
    is_holiday_ca_observed TEXT,
    is_dst_transition_day TEXT,
    hdh_65 TEXT,
    cdh_65 TEXT,
    hdd_65_daily TEXT,
    cdd_65_daily TEXT,
    weather_is_preliminary TEXT,
    _batch_id TEXT NOT NULL,
    _source_file TEXT NOT NULL,
    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_caiso_hourly_batch_id
    ON raw_data.raw_caiso_hourly (_batch_id);

-- Tracks ingestion attempts for traceability; raw CSV fields stay TEXT to preserve their source values.
CREATE TABLE IF NOT EXISTS raw_data.ingestion_log (
    batch_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    source TEXT,
    http_status INT,
    source_file TEXT,
    sha256 TEXT,
    rows_fetched BIGINT,
    rows_loaded BIGINT,
    status TEXT,
    error TEXT
);
