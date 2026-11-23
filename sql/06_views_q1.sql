-- Q1: Aggregate hourly demand by 2-degree population-weighted temperature bins.
-- The floor expression labels each bin by its lower Celsius bound.
CREATE OR REPLACE VIEW dw.v_q1_demand_by_temp_bin AS
SELECT
    FLOOR(weather.temp_pop_wt_c / 2.0) * 2 AS temp_bin_c,
    COUNT(*) AS hours_count,
    AVG(demand.demand_mwh) AS avg_demand_mwh,
    STDDEV_SAMP(demand.demand_mwh) AS stddev_demand_mwh
FROM dw.fact_demand AS demand
JOIN dw.fact_weather_weighted AS weather
  ON weather.datetime_id = demand.datetime_id
JOIN dw.dim_datetime AS datetime
  ON datetime.datetime_id = demand.datetime_id
WHERE weather.temp_pop_wt_c IS NOT NULL
GROUP BY FLOOR(weather.temp_pop_wt_c / 2.0) * 2;

-- Q1: Compare each bin's average demand with the prior temperature bin.
-- LAG and the difference make the first strong upward change visible.
CREATE OR REPLACE VIEW dw.v_q1_demand_slope AS
SELECT
    temp_bin_c,
    hours_count,
    avg_demand_mwh,
    stddev_demand_mwh,
    LAG(avg_demand_mwh) OVER (ORDER BY temp_bin_c)
        AS previous_bin_avg_demand_mwh,
    avg_demand_mwh
        - LAG(avg_demand_mwh) OVER (ORDER BY temp_bin_c)
        AS demand_increase_from_previous_bin_mwh
FROM dw.v_q1_demand_by_temp_bin;
