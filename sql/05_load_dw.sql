-- Created as fallback for Basel Tamer Fathy; merge/replace if his PR lands.
-- The caller owns the transaction; this full refresh intentionally contains no COMMIT.
-- All referencing facts are listed before their dimensions, so CASCADE is unnecessary.
TRUNCATE TABLE
    dw.fact_city_temperature,
    dw.fact_weather_weighted,
    dw.fact_demand,
    dw.dim_datetime,
    dw.dim_holiday,
    dw.dim_city;

-- Assign stable IDs to the distinct combinations of source holiday flags.
INSERT INTO dw.dim_holiday (
    holiday_id,
    is_holiday_statutory,
    is_holiday_observed,
    is_holiday_ca_statutory,
    is_holiday_ca_observed
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY
            is_holiday_statutory,
            is_holiday_observed,
            is_holiday_ca_statutory,
            is_holiday_ca_observed
    )::SMALLINT,
    is_holiday_statutory,
    is_holiday_observed,
    is_holiday_ca_statutory,
    is_holiday_ca_observed
FROM (
    SELECT DISTINCT
        is_holiday_statutory,
        is_holiday_observed,
        is_holiday_ca_statutory,
        is_holiday_ca_observed
    FROM clean_data.stg_caiso_clean
) AS holiday_flags;

INSERT INTO dw.dim_city (city_id, city_name) VALUES
    (1, 'Los Angeles'),
    (2, 'Riverside'),
    (3, 'San Diego'),
    (4, 'San Francisco'),
    (5, 'San Jose'),
    (6, 'Sacramento'),
    (7, 'Fresno');

-- datetime_id is reproducible because each full refresh orders rows by unique datetime_utc.
-- Seasons use meteorological months: Dec-Feb winter, Mar-May spring, Jun-Aug summer, Sep-Nov fall.
INSERT INTO dw.dim_datetime (
    datetime_id,
    datetime_utc,
    datetime_local,
    year,
    month,
    season,
    hour,
    day_of_week,
    is_weekend,
    is_dst_transition_day,
    holiday_id
)
SELECT
    ROW_NUMBER() OVER (ORDER BY stg.datetime_utc)::BIGINT,
    stg.datetime_utc,
    stg.datetime_local,
    EXTRACT(YEAR FROM stg.datetime_local)::SMALLINT,
    EXTRACT(MONTH FROM stg.datetime_local)::SMALLINT,
    CASE
        WHEN EXTRACT(MONTH FROM stg.datetime_local) IN (12, 1, 2)
            THEN 'winter'
        WHEN EXTRACT(MONTH FROM stg.datetime_local) IN (3, 4, 5)
            THEN 'spring'
        WHEN EXTRACT(MONTH FROM stg.datetime_local) IN (6, 7, 8)
            THEN 'summer'
        ELSE 'fall'
    END,
    stg.hour,
    stg.day_of_week,
    stg.is_weekend,
    stg.is_dst_transition_day,
    holiday.holiday_id
FROM clean_data.stg_caiso_clean AS stg
JOIN dw.dim_holiday AS holiday
  ON holiday.is_holiday_statutory = stg.is_holiday_statutory
 AND holiday.is_holiday_observed = stg.is_holiday_observed
 AND holiday.is_holiday_ca_statutory = stg.is_holiday_ca_statutory
 AND holiday.is_holiday_ca_observed = stg.is_holiday_ca_observed;

INSERT INTO dw.fact_demand (
    datetime_id,
    demand_mwh,
    demand_reported_mwh,
    demand_imputed_pudl_mwh,
    demand_imputed_pudl_mwh_imputation_code,
    demand_is_imputed,
    demand_source
)
SELECT
    dt.datetime_id,
    stg.demand_mwh,
    stg.demand_reported_mwh,
    stg.demand_imputed_pudl_mwh,
    stg.demand_imputed_pudl_mwh_imputation_code,
    stg.demand_is_imputed,
    stg.demand_source
FROM clean_data.stg_caiso_clean AS stg
JOIN dw.dim_datetime AS dt
  ON dt.datetime_utc = stg.datetime_utc;

INSERT INTO dw.fact_weather_weighted (
    datetime_id,
    temp_pop_wt_c,
    temp_pop_wt_f,
    shortwave_radiation_pop_wt_wm2,
    cloud_cover_pop_wt_pct,
    hdh_65,
    cdh_65,
    hdd_65_daily,
    cdd_65_daily,
    weather_is_preliminary,
    temp_is_missing,
    temp_is_imputed
)
SELECT
    dt.datetime_id,
    stg.temp_pop_wt_c,
    stg.temp_pop_wt_f,
    stg.shortwave_radiation_pop_wt_wm2,
    stg.cloud_cover_pop_wt_pct,
    stg.hdh_65,
    stg.cdh_65,
    stg.hdd_65_daily,
    stg.cdd_65_daily,
    stg.weather_is_preliminary,
    stg.temp_is_missing,
    stg.temp_is_imputed
FROM clean_data.stg_caiso_clean AS stg
JOIN dw.dim_datetime AS dt
  ON dt.datetime_utc = stg.datetime_utc;

INSERT INTO dw.fact_city_temperature (datetime_id, city_id, temp_c)
SELECT
    dt.datetime_id,
    city.city_id,
    temperature.temp_c
FROM clean_data.stg_caiso_clean AS stg
JOIN dw.dim_datetime AS dt
  ON dt.datetime_utc = stg.datetime_utc
CROSS JOIN LATERAL (
    VALUES
        ('Los Angeles', stg.temp_c_los_angeles),
        ('Riverside', stg.temp_c_riverside),
        ('San Diego', stg.temp_c_san_diego),
        ('San Francisco', stg.temp_c_san_francisco),
        ('San Jose', stg.temp_c_san_jose),
        ('Sacramento', stg.temp_c_sacramento),
        ('Fresno', stg.temp_c_fresno)
) AS temperature(city_name, temp_c)
JOIN dw.dim_city AS city
  ON city.city_name = temperature.city_name;
