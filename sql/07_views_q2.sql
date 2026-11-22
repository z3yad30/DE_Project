-- Q2 daily load shape: compare hourly demand with population-weighted solar
-- radiation and cloud cover by year, meteorological season, and local hour.
CREATE OR REPLACE VIEW dw.v_q2_load_shape_by_year_season_hour AS
SELECT
    dt.year,
    dt.season,
    dt.hour AS local_hour,
    AVG(fd.demand_mwh) AS avg_demand_mwh,
    AVG(fw.shortwave_radiation_pop_wt_wm2)
        AS avg_shortwave_radiation_pop_wt_wm2,
    AVG(fw.cloud_cover_pop_wt_pct) AS avg_cloud_cover_pop_wt_pct
FROM dw.fact_demand AS fd
JOIN dw.fact_weather_weighted AS fw
  ON fw.datetime_id = fd.datetime_id
JOIN dw.dim_datetime AS dt
  ON dt.datetime_id = fd.datetime_id
GROUP BY
    dt.year,
    dt.season,
    dt.hour;

-- Q2 midday dip: evening-ramp average (local hours 17-19) minus midday
-- average (local hours 11-14); a larger value means a deeper midday dip
-- relative to the evening ramp.
CREATE OR REPLACE VIEW dw.v_q2_midday_dip AS
SELECT
    dt.year,
    dt.season,
    AVG(fd.demand_mwh) FILTER (WHERE dt.hour BETWEEN 11 AND 14)
        AS midday_avg_demand_mwh,
    AVG(fd.demand_mwh) FILTER (WHERE dt.hour BETWEEN 17 AND 19)
        AS evening_ramp_avg_demand_mwh,
    AVG(fd.demand_mwh) FILTER (WHERE dt.hour BETWEEN 17 AND 19)
      - AVG(fd.demand_mwh) FILTER (WHERE dt.hour BETWEEN 11 AND 14)
        AS midday_dip_mwh
FROM dw.fact_demand AS fd
JOIN dw.fact_weather_weighted AS fw
  ON fw.datetime_id = fd.datetime_id
JOIN dw.dim_datetime AS dt
  ON dt.datetime_id = fd.datetime_id
GROUP BY
    dt.year,
    dt.season;
