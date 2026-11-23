
-- Task 4: Post-load data quality checks
-- Each query returns the number of violations.
-- A result of zero means the check passed.

-- 1. Duplicate primary-key checks

SELECT 'dim_holiday_pk' AS check_name, COUNT(*) AS offending_count
FROM (
    SELECT holiday_id
    FROM dw.dim_holiday
    GROUP BY holiday_id
    HAVING COUNT(*) > 1
) AS duplicates;

SELECT 'dim_datetime_pk' AS check_name, COUNT(*) AS offending_count
FROM (
    SELECT datetime_id
    FROM dw.dim_datetime
    GROUP BY datetime_id
    HAVING COUNT(*) > 1
) AS duplicates;

SELECT 'dim_city_pk' AS check_name, COUNT(*) AS offending_count
FROM (
    SELECT city_id
    FROM dw.dim_city
    GROUP BY city_id
    HAVING COUNT(*) > 1
) AS duplicates;

SELECT 'fact_demand_pk' AS check_name, COUNT(*) AS offending_count
FROM (
    SELECT datetime_id
    FROM dw.fact_demand
    GROUP BY datetime_id
    HAVING COUNT(*) > 1
) AS duplicates;

SELECT 'fact_weather_pk' AS check_name, COUNT(*) AS offending_count
FROM (
    SELECT datetime_id
    FROM dw.fact_weather_weighted
    GROUP BY datetime_id
    HAVING COUNT(*) > 1
) AS duplicates;

SELECT 'fact_city_temperature_pk' AS check_name, COUNT(*) AS offending_count
FROM (
    SELECT datetime_id, city_id
    FROM dw.fact_city_temperature
    GROUP BY datetime_id, city_id
    HAVING COUNT(*) > 1
) AS duplicates;


-- 2. Foreign-key integrity checks

SELECT 'datetime_holiday_fk' AS check_name, COUNT(*) AS offending_count
FROM dw.dim_datetime dt
LEFT JOIN dw.dim_holiday h ON h.holiday_id = dt.holiday_id
WHERE h.holiday_id IS NULL;

SELECT 'demand_datetime_fk' AS check_name, COUNT(*) AS offending_count
FROM dw.fact_demand f
LEFT JOIN dw.dim_datetime dt ON dt.datetime_id = f.datetime_id
WHERE dt.datetime_id IS NULL;

SELECT 'weather_datetime_fk' AS check_name, COUNT(*) AS offending_count
FROM dw.fact_weather_weighted f
LEFT JOIN dw.dim_datetime dt ON dt.datetime_id = f.datetime_id
WHERE dt.datetime_id IS NULL;

SELECT 'city_temperature_datetime_fk' AS check_name, COUNT(*) AS offending_count
FROM dw.fact_city_temperature f
LEFT JOIN dw.dim_datetime dt ON dt.datetime_id = f.datetime_id
WHERE dt.datetime_id IS NULL;

SELECT 'city_temperature_city_fk' AS check_name, COUNT(*) AS offending_count
FROM dw.fact_city_temperature f
LEFT JOIN dw.dim_city c ON c.city_id = f.city_id
WHERE c.city_id IS NULL;


-- 3. NULL percentage checks
-- Thresholds are percentages, not fractions.

SELECT 'demand_reported_null_pct' AS check_name,
       COUNT(*) FILTER (WHERE demand_reported_mwh IS NULL) * 100.0
       / NULLIF(COUNT(*), 0) AS offending_count
FROM dw.fact_demand;

SELECT 'demand_imputed_null_pct' AS check_name,
       COUNT(*) FILTER (WHERE demand_imputed_pudl_mwh IS NULL) * 100.0
       / NULLIF(COUNT(*), 0) AS offending_count
FROM dw.fact_demand;

SELECT 'hdd_daily_null_pct' AS check_name,
       COUNT(*) FILTER (WHERE hdd_65_daily IS NULL) * 100.0
       / NULLIF(COUNT(*), 0) AS offending_count
FROM dw.fact_weather_weighted;

SELECT 'cdd_daily_null_pct' AS check_name,
       COUNT(*) FILTER (WHERE cdd_65_daily IS NULL) * 100.0
       / NULLIF(COUNT(*), 0) AS offending_count
FROM dw.fact_weather_weighted;


-- 4. Value-range checks

SELECT 'invalid_demand' AS check_name, COUNT(*) AS offending_count
FROM dw.fact_demand
WHERE demand_mwh IS NULL OR demand_mwh <= 0;

SELECT 'invalid_cloud_cover' AS check_name, COUNT(*) AS offending_count
FROM dw.fact_weather_weighted
WHERE cloud_cover_pop_wt_pct < 0
   OR cloud_cover_pop_wt_pct > 100;

SELECT 'negative_weather_measurements' AS check_name, COUNT(*) AS offending_count
FROM dw.fact_weather_weighted
WHERE shortwave_radiation_pop_wt_wm2 < 0
   OR hdh_65 < 0
   OR cdh_65 < 0
   OR hdd_65_daily < 0
   OR cdd_65_daily < 0;

SELECT 'invalid_datetime_month' AS check_name, COUNT(*) AS offending_count
FROM dw.dim_datetime
WHERE month NOT BETWEEN 1 AND 12;

SELECT 'invalid_datetime_hour' AS check_name, COUNT(*) AS offending_count
FROM dw.dim_datetime
WHERE hour NOT BETWEEN 0 AND 23;

SELECT 'invalid_datetime_weekday' AS check_name, COUNT(*) AS offending_count
FROM dw.dim_datetime
WHERE day_of_week NOT BETWEEN 0 AND 6;


-- 5. Raw staging versus warehouse row counts

SELECT 'staging_vs_datetime' AS check_name,
       ABS(
           (SELECT COUNT(*) FROM clean_data.stg_caiso_clean) -
           (SELECT COUNT(*) FROM dw.dim_datetime)
       ) AS offending_count;

SELECT 'staging_vs_demand' AS check_name,
       ABS(
           (SELECT COUNT(*) FROM clean_data.stg_caiso_clean) -
           (SELECT COUNT(*) FROM dw.fact_demand)
       ) AS offending_count;

SELECT 'staging_vs_weather' AS check_name,
       ABS(
           (SELECT COUNT(*) FROM clean_data.stg_caiso_clean) -
           (SELECT COUNT(*) FROM dw.fact_weather_weighted)
       ) AS offending_count;

SELECT 'staging_vs_city_temperature' AS check_name,
       ABS(
           (SELECT COUNT(*) * 7 FROM clean_data.stg_caiso_clean) -
           (SELECT COUNT(*) FROM dw.fact_city_temperature)
       ) AS offending_count;
