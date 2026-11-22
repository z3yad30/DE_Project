-- Q3: Compare electricity demand patterns across local hours for weekdays/weekends and holidays.
CREATE OR REPLACE VIEW dw.v_q3_peak_by_hour_weekend_holiday AS
SELECT
    dt.hour AS local_hour,
    dt.is_weekend,
    COALESCE(dh.is_holiday, FALSE) AS is_holiday,
    AVG(fd.demand_mwh) AS avg_demand_mwh,
    MAX(fd.demand_mwh) AS max_demand_mwh
FROM dw.fact_demand AS fd
JOIN dw.dim_datetime AS dt
  ON dt.datetime_utc = fd.datetime_utc
LEFT JOIN dw.dim_holiday AS dh
  ON dh.holiday_date = DATE(dt.datetime_local)
GROUP BY dt.hour, dt.is_weekend, COALESCE(dh.is_holiday, FALSE);

-- Q3: Rank the seven cities by the absolute correlation between city temperature and demand.
CREATE OR REPLACE VIEW dw.v_q3_city_temp_demand_corr AS
WITH correlations AS (
    SELECT
        dc.city_id,
        dc.city_name,
        CORR(fct.temp_c, fd.demand_mwh) AS temperature_demand_corr
    FROM dw.fact_city_temperature AS fct
    JOIN dw.dim_city AS dc
      ON dc.city_id = fct.city_id
    JOIN dw.fact_demand AS fd
      ON fd.datetime_utc = fct.datetime_utc
    GROUP BY dc.city_id, dc.city_name
)
SELECT
    city_id,
    city_name,
    temperature_demand_corr,
    RANK() OVER (
        ORDER BY ABS(temperature_demand_corr) DESC NULLS LAST
    ) AS correlation_rank
FROM correlations;
