-- Created as fallback for Basel Tamer Fathy; merge/replace if his PR lands.
CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.dim_holiday (
    holiday_id SMALLINT PRIMARY KEY,
    is_holiday_statutory BOOLEAN NOT NULL,
    is_holiday_observed BOOLEAN NOT NULL,
    is_holiday_ca_statutory BOOLEAN NOT NULL,
    is_holiday_ca_observed BOOLEAN NOT NULL,
    CONSTRAINT uq_dim_holiday_flags UNIQUE (
        is_holiday_statutory,
        is_holiday_observed,
        is_holiday_ca_statutory,
        is_holiday_ca_observed
    )
);

CREATE TABLE IF NOT EXISTS dw.dim_datetime (
    datetime_id BIGINT PRIMARY KEY,
    datetime_utc TIMESTAMPTZ NOT NULL UNIQUE,
    datetime_local TIMESTAMP NOT NULL,
    year SMALLINT NOT NULL,
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    season TEXT NOT NULL CHECK (season IN ('winter', 'spring', 'summer', 'fall')),
    hour SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    is_weekend BOOLEAN NOT NULL,
    is_dst_transition_day BOOLEAN NOT NULL,
    holiday_id SMALLINT NOT NULL REFERENCES dw.dim_holiday(holiday_id)
);

CREATE TABLE IF NOT EXISTS dw.dim_city (
    city_id SMALLINT PRIMARY KEY,
    city_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dw.fact_demand (
    datetime_id BIGINT PRIMARY KEY REFERENCES dw.dim_datetime(datetime_id),
    demand_mwh NUMERIC NOT NULL CHECK (demand_mwh > 0),
    demand_reported_mwh NUMERIC,
    demand_imputed_pudl_mwh NUMERIC,
    demand_imputed_pudl_mwh_imputation_code TEXT,
    demand_is_imputed BOOLEAN,
    demand_source TEXT
);

CREATE TABLE IF NOT EXISTS dw.fact_weather_weighted (
    datetime_id BIGINT PRIMARY KEY REFERENCES dw.dim_datetime(datetime_id),
    temp_pop_wt_c NUMERIC,
    temp_pop_wt_f NUMERIC,
    shortwave_radiation_pop_wt_wm2 NUMERIC
        CHECK (shortwave_radiation_pop_wt_wm2 >= 0),
    cloud_cover_pop_wt_pct NUMERIC
        CHECK (cloud_cover_pop_wt_pct BETWEEN 0 AND 100),
    hdh_65 NUMERIC CHECK (hdh_65 >= 0),
    cdh_65 NUMERIC CHECK (cdh_65 >= 0),
    hdd_65_daily NUMERIC CHECK (hdd_65_daily >= 0),
    cdd_65_daily NUMERIC CHECK (cdd_65_daily >= 0),
    weather_is_preliminary BOOLEAN,
    temp_is_missing BOOLEAN,
    temp_is_imputed BOOLEAN
);

CREATE TABLE IF NOT EXISTS dw.fact_city_temperature (
    datetime_id BIGINT NOT NULL REFERENCES dw.dim_datetime(datetime_id),
    city_id SMALLINT NOT NULL REFERENCES dw.dim_city(city_id),
    temp_c NUMERIC,
    CONSTRAINT pk_fact_city_temperature PRIMARY KEY (datetime_id, city_id)
);

-- This index accelerates dim_datetime lookups by the holiday lookup foreign key.
CREATE INDEX IF NOT EXISTS idx_dim_datetime_holiday_id
    ON dw.dim_datetime (holiday_id);
COMMENT ON INDEX dw.idx_dim_datetime_holiday_id IS
    'Supports joins from local datetime rows to holiday flag combinations.';

-- This index supports date, season, and hour filters used by analytical views.
CREATE INDEX IF NOT EXISTS idx_dim_datetime_year_month_hour
    ON dw.dim_datetime (year, month, hour);
COMMENT ON INDEX dw.idx_dim_datetime_year_month_hour IS
    'Supports grouping and filtering datetime rows by year, month, and local hour.';

-- This index supports the datetime foreign key on the demand fact.
CREATE INDEX IF NOT EXISTS idx_fact_demand_datetime_id
    ON dw.fact_demand (datetime_id);
COMMENT ON INDEX dw.idx_fact_demand_datetime_id IS
    'Supports fact-to-datetime joins and foreign-key validation.';

-- This index supports the datetime foreign key on the weighted weather fact.
CREATE INDEX IF NOT EXISTS idx_fact_weather_weighted_datetime_id
    ON dw.fact_weather_weighted (datetime_id);
COMMENT ON INDEX dw.idx_fact_weather_weighted_datetime_id IS
    'Supports fact-to-datetime joins and foreign-key validation.';

-- This index supports datetime joins for the long city-temperature fact.
CREATE INDEX IF NOT EXISTS idx_fact_city_temperature_datetime_id
    ON dw.fact_city_temperature (datetime_id);
COMMENT ON INDEX dw.idx_fact_city_temperature_datetime_id IS
    'Supports fact-to-datetime joins and foreign-key validation.';

-- This index supports city filtering and city foreign-key validation.
CREATE INDEX IF NOT EXISTS idx_fact_city_temperature_city_id
    ON dw.fact_city_temperature (city_id);
COMMENT ON INDEX dw.idx_fact_city_temperature_city_id IS
    'Supports city-to-temperature joins and foreign-key validation.';
