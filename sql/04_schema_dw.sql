-- Created as fallback for Basel Tamer Fathy; merge/replace if his PR lands.
CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.dim_datetime (
    datetime_utc TIMESTAMPTZ PRIMARY KEY,
    datetime_local TIMESTAMP,
    hour SMALLINT,
    day_of_week SMALLINT,
    month SMALLINT,
    is_weekend BOOLEAN
);

CREATE TABLE IF NOT EXISTS dw.dim_holiday (
    holiday_date DATE PRIMARY KEY,
    holiday_name TEXT,
    is_holiday BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dw.dim_city (
    city_id SMALLINT PRIMARY KEY,
    city_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.fact_demand (
    datetime_utc TIMESTAMPTZ PRIMARY KEY,
    demand_mwh NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.fact_weather_weighted (
    datetime_utc TIMESTAMPTZ PRIMARY KEY,
    temp_pop_wt_c NUMERIC,
    temp_pop_wt_f NUMERIC,
    shortwave_radiation_pop_wt_wm2 NUMERIC,
    cloud_cover_pop_wt_pct NUMERIC
);

CREATE TABLE IF NOT EXISTS dw.fact_city_temperature (
    datetime_utc TIMESTAMPTZ NOT NULL,
    city_id SMALLINT NOT NULL REFERENCES dw.dim_city(city_id),
    temp_c NUMERIC,
    PRIMARY KEY (datetime_utc, city_id)
);
