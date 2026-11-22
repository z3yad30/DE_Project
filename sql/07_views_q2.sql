-- Question 2 (Part A): Hourly demand shape, solar irradiance, and cloud cover
-- grouped by year, season, and local hour across the warehouse tables.
CREATE OR REPLACE VIEW dw.v_q2_hourly_load_solar AS
WITH city_temp_hourly AS (
    SELECT
        datetime_id,
        AVG(temp_c) AS avg_city_temp_c
    FROM dw.fact_city_temperature
    GROUP BY datetime_id
)
SELECT
    d.year,
    d.season,
    d.hour AS local_hour,
    ROUND(AVG(fd.demand_mwh)::numeric, 2) AS avg_demand_mwh,
    ROUND(AVG(fw.shortwave_radiation_pop_wt_wm2)::numeric, 2) AS avg_shortwave_radiation_wm2,
    ROUND(AVG(fw.cloud_cover_pop_wt_pct)::numeric, 2) AS avg_cloud_cover_pct,
    ROUND(AVG(fw.temp_pop_wt_c)::numeric, 2) AS avg_pop_wt_temp_c,
    ROUND(AVG(ct.avg_city_temp_c)::numeric, 2) AS avg_city_temp_c,
    COUNT(*) AS sample_hours
FROM dw.fact_demand fd
JOIN dw.dim_datetime d
    ON fd.datetime_id = d.datetime_id
JOIN dw.fact_weather_weighted fw
    ON fd.datetime_id = fw.datetime_id
LEFT JOIN city_temp_hourly ct
    ON fd.datetime_id = ct.datetime_id
GROUP BY
    d.year,
    d.season,
    d.hour;

-- Question 2 (Part B): Midday-dip metric per year and season.
-- Definition: AVG(demand_mwh for local hours 17..19) - AVG(demand_mwh for local hours 11..14).
-- A higher positive value means a deeper midday dip relative to the evening ramp.
CREATE OR REPLACE VIEW dw.v_q2_midday_dip AS
WITH seasonal_hourly AS (
    SELECT
        d.year,
        d.season,
        d.hour AS local_hour,
        AVG(fd.demand_mwh) AS hourly_avg_demand_mwh,
        AVG(fw.shortwave_radiation_pop_wt_wm2) AS hourly_avg_solar_wm2,
        AVG(fw.cloud_cover_pop_wt_pct) AS hourly_avg_cloud_pct
    FROM dw.fact_demand fd
    JOIN dw.dim_datetime d
        ON fd.datetime_id = d.datetime_id
    JOIN dw.fact_weather_weighted fw
        ON fd.datetime_id = fw.datetime_id
    GROUP BY
        d.year,
        d.season,
        d.hour
)
SELECT
    year,
    season,
    ROUND(AVG(hourly_avg_demand_mwh) FILTER (WHERE local_hour BETWEEN 11 AND 14)::numeric, 2) AS midday_avg_demand_mwh,
    ROUND(AVG(hourly_avg_demand_mwh) FILTER (WHERE local_hour BETWEEN 17 AND 19)::numeric, 2) AS evening_ramp_avg_demand_mwh,
    ROUND(
        (
            AVG(hourly_avg_demand_mwh) FILTER (WHERE local_hour BETWEEN 17 AND 19)
            - AVG(hourly_avg_demand_mwh) FILTER (WHERE local_hour BETWEEN 11 AND 14)
        )::numeric,
        2
    ) AS midday_dip_mwh,
    ROUND(AVG(hourly_avg_solar_wm2) FILTER (WHERE local_hour BETWEEN 11 AND 14)::numeric, 2) AS midday_avg_solar_wm2,
    ROUND(AVG(hourly_avg_cloud_pct) FILTER (WHERE local_hour BETWEEN 11 AND 14)::numeric, 2) AS midday_avg_cloud_pct
FROM seasonal_hourly
GROUP BY
    year,
    season
ORDER BY
    year,
    season;
