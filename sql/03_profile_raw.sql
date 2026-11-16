SET timezone = 'UTC';

CREATE OR REPLACE TEMP VIEW latest_batch AS
SELECT *
FROM raw_data.raw_caiso_hourly
WHERE _batch_id = (
    SELECT _batch_id
    FROM raw_data.raw_caiso_hourly
    GROUP BY _batch_id
    ORDER BY max(_ingested_at) DESC
    LIMIT 1
);

DROP TABLE IF EXISTS pg_temp._profile_cols;
CREATE TEMP TABLE _profile_cols (col TEXT PRIMARY KEY, kind TEXT NOT NULL);
INSERT INTO _profile_cols (col, kind) VALUES
 ('datetime_utc','timestamp'), ('datetime_local','timestamp'),
 ('demand_mwh','float'), ('demand_reported_mwh','float'), ('demand_imputed_pudl_mwh','float'),
 ('temp_c_los_angeles','float'), ('temp_c_riverside','float'), ('temp_c_san_diego','float'),
 ('temp_c_san_francisco','float'), ('temp_c_san_jose','float'), ('temp_c_sacramento','float'),
 ('temp_c_fresno','float'), ('temp_pop_wt_c','float'), ('temp_pop_wt_f','float'),
 ('shortwave_radiation_pop_wt_wm2','float'), ('cloud_cover_pop_wt_pct','float'),
 ('hdh_65','float'), ('cdh_65','float'), ('hdd_65_daily','float'), ('cdd_65_daily','float'),
 ('hour','integer'), ('day_of_week','integer'), ('month','integer'),
 ('demand_is_imputed','boolean'), ('temp_is_missing','boolean'), ('temp_is_imputed','boolean'),
 ('is_weekend','boolean'), ('is_holiday_statutory','boolean'), ('is_holiday_observed','boolean'),
 ('is_holiday_ca_statutory','boolean'), ('is_holiday_ca_observed','boolean'),
 ('is_dst_transition_day','boolean'), ('weather_is_preliminary','boolean'),
 ('demand_source','string'), ('demand_imputed_pudl_mwh_imputation_code','string');

CREATE OR REPLACE FUNCTION pg_temp.try_float(v TEXT) RETURNS DOUBLE PRECISION AS $$
BEGIN
    IF v IS NULL OR btrim(v) = '' OR v !~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' THEN
        RETURN NULL;
    END IF;
    RETURN v::double precision;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pg_temp.try_ts(v TEXT) RETURNS TIMESTAMPTZ AS $$
BEGIN
    RETURN v::timestamptz;      
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pg_temp.try_wall(v TEXT) RETURNS TIMESTAMP AS $$
BEGIN
    RETURN v::timestamp;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TEMP VIEW profile_typed AS
SELECT
    pg_temp.try_ts(datetime_utc)     AS utc_ts,
    pg_temp.try_wall(datetime_utc)   AS utc_wall,
    pg_temp.try_wall(datetime_local) AS local_wall,
    pg_temp.try_float(demand_mwh)                      AS demand_mwh_n,
    pg_temp.try_float(cloud_cover_pop_wt_pct)          AS cloud_n,
    pg_temp.try_float(shortwave_radiation_pop_wt_wm2)  AS shortwave_n,
    pg_temp.try_float(temp_pop_wt_c)                   AS temp_pop_c_n,
    pg_temp.try_float(temp_pop_wt_f)                   AS temp_pop_f_n,
    pg_temp.try_float(temp_c_los_angeles)    AS t_la,
    pg_temp.try_float(temp_c_riverside)      AS t_riv,
    pg_temp.try_float(temp_c_san_diego)      AS t_sd,
    pg_temp.try_float(temp_c_san_francisco)  AS t_sf,
    pg_temp.try_float(temp_c_san_jose)       AS t_sj,
    pg_temp.try_float(temp_c_sacramento)     AS t_sac,
    pg_temp.try_float(temp_c_fresno)         AS t_fre,
    pg_temp.try_float(hdh_65)       AS hdh_n,
    pg_temp.try_float(cdh_65)       AS cdh_n,
    pg_temp.try_float(hdd_65_daily) AS hdd_n,
    pg_temp.try_float(cdd_65_daily) AS cdd_n,
    pg_temp.try_float(hour)         AS hour_n,
    pg_temp.try_float(month)        AS month_n,
    pg_temp.try_float(day_of_week)  AS dow_n,
    is_weekend, is_dst_transition_day
FROM latest_batch;


SELECT _batch_id, _source_file, count(*) AS rows_in_batch,
       max(_ingested_at) AS last_ingested_at
FROM raw_data.raw_caiso_hourly
GROUP BY 1, 2
ORDER BY 4 DESC;


SELECT count(*)                                AS total_rows,
       count(DISTINCT datetime_utc)            AS distinct_non_null_datetime_utc,
       count(*) FILTER (WHERE datetime_utc IS NOT NULL)
         - count(DISTINCT datetime_utc)        AS extra_rows_for_non_null_timestamps,
       count(*) FILTER (WHERE datetime_utc IS NULL) AS rows_with_null_datetime_utc,
       min(datetime_utc)                       AS min_datetime_utc_text,
       max(datetime_utc)                       AS max_datetime_utc_text
FROM latest_batch;

SELECT min(utc_ts) AS min_datetime_utc, max(utc_ts) AS max_datetime_utc
FROM profile_typed;


SELECT datetime_utc, count(*) AS n
FROM latest_batch
WHERE datetime_utc IS NOT NULL
GROUP BY 1
HAVING count(*) > 1
ORDER BY n DESC, 1
LIMIT 50;

SELECT
    (SELECT count(*) FROM (SELECT 1 FROM latest_batch WHERE datetime_utc IS NOT NULL
                          GROUP BY datetime_utc HAVING count(*) > 1) d)
        AS duplicated_non_null_timestamp_groups,
    (SELECT count(*) FILTER (WHERE datetime_utc IS NOT NULL)
            - count(DISTINCT datetime_utc) FROM latest_batch)
        AS extra_rows_by_non_null_timestamp,
    (SELECT count(*) - count(DISTINCT (to_jsonb(t) - '{_batch_id,_source_file,_ingested_at}'::text[]))
       FROM latest_batch t)
        AS fully_identical_extra_rows;

SELECT count(*) AS timestamps_with_conflicting_rows
FROM (
    SELECT datetime_utc
    FROM latest_batch t
    WHERE datetime_utc IS NOT NULL
    GROUP BY datetime_utc
    HAVING count(DISTINCT (to_jsonb(t) - '{_batch_id,_source_file,_ingested_at}'::text[])) > 1
) c;


SELECT count(*) - count(DISTINCT utc_ts) AS extra_rows_by_parsed_timestamp
FROM profile_typed
WHERE utc_ts IS NOT NULL;


SELECT j.key AS column_name,
       count(*) FILTER (WHERE j.value IS NULL OR btrim(j.value) = '') AS missing_count,
       round(100.0 * count(*) FILTER (WHERE j.value IS NULL OR btrim(j.value) = '')
             / (SELECT count(*) FROM latest_batch), 3)                AS missing_pct
FROM latest_batch t, LATERAL jsonb_each_text(to_jsonb(t)) j
WHERE left(j.key, 1) <> '_'            
GROUP BY 1
ORDER BY 2 DESC, 1;


SELECT j.key AS column_name,
       count(*) FILTER (
           WHERE j.value IS NOT NULL AND btrim(j.value) <> ''
             AND j.value !~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$'
       ) AS invalid_count,
       round(100.0 * count(*) FILTER (
           WHERE j.value IS NOT NULL AND btrim(j.value) <> ''
             AND j.value !~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$'
       ) / (SELECT count(*) FROM latest_batch), 3) AS invalid_pct
FROM latest_batch t
     CROSS JOIN LATERAL jsonb_each_text(to_jsonb(t)) j
     JOIN _profile_cols c ON c.col = j.key AND c.kind IN ('float', 'integer')
GROUP BY 1
ORDER BY 2 DESC, 1;

SELECT j.key AS column_name, j.value AS invalid_value, count(*) AS n
FROM latest_batch t
     CROSS JOIN LATERAL jsonb_each_text(to_jsonb(t)) j
     JOIN _profile_cols c ON c.col = j.key AND c.kind IN ('float', 'integer')
WHERE j.value IS NOT NULL AND btrim(j.value) <> ''
  AND j.value !~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$'
GROUP BY 1, 2
ORDER BY 3 DESC
LIMIT 30;


SELECT j.key AS column_name, count(*) AS non_integer_values
FROM latest_batch t
     CROSS JOIN LATERAL jsonb_each_text(to_jsonb(t)) j
     JOIN _profile_cols c ON c.col = j.key AND c.kind = 'integer'
WHERE pg_temp.try_float(j.value) <> trunc(pg_temp.try_float(j.value))
GROUP BY 1
ORDER BY 1;


SELECT j.key AS column_name, j.value AS spelling, count(*) AS n
FROM latest_batch t
     CROSS JOIN LATERAL jsonb_each_text(to_jsonb(t)) j
     JOIN _profile_cols c ON c.col = j.key AND c.kind = 'boolean'
GROUP BY 1, 2
ORDER BY 1, 2;

SELECT j.key AS column_name, count(DISTINCT j.value) AS distinct_spellings
FROM latest_batch t
     CROSS JOIN LATERAL jsonb_each_text(to_jsonb(t)) j
     JOIN _profile_cols c ON c.col = j.key AND c.kind = 'boolean'
GROUP BY 1
ORDER BY 2 DESC, 1;

WITH checks AS (
    SELECT 'demand_mwh <= 0' AS issue, count(*) FILTER (WHERE demand_mwh_n <= 0) AS n FROM profile_typed
    UNION ALL SELECT 'cloud_cover_pop_wt_pct < 0',   count(*) FILTER (WHERE cloud_n < 0)   FROM profile_typed
    UNION ALL SELECT 'cloud_cover_pop_wt_pct > 100', count(*) FILTER (WHERE cloud_n > 100) FROM profile_typed
    UNION ALL SELECT 'shortwave_radiation_pop_wt_wm2 < 0', count(*) FILTER (WHERE shortwave_n < 0) FROM profile_typed
    UNION ALL SELECT 'temp_pop_wt_c outside -10..50',
        count(*) FILTER (WHERE temp_pop_c_n < -10 OR temp_pop_c_n > 50) FROM profile_typed
    UNION ALL SELECT 'any temp_c_<city> outside -10..50',
        count(*) FILTER (WHERE t_la  < -10 OR t_la  > 50 OR t_riv < -10 OR t_riv > 50
                            OR t_sd  < -10 OR t_sd  > 50 OR t_sf  < -10 OR t_sf  > 50
                            OR t_sj  < -10 OR t_sj  > 50 OR t_sac < -10 OR t_sac > 50
                            OR t_fre < -10 OR t_fre > 50) FROM profile_typed
    UNION ALL SELECT 'temp_pop_wt_f != temp_pop_wt_c*9/5+32 (tolerance 0.5)',
        count(*) FILTER (WHERE temp_pop_c_n IS NOT NULL AND temp_pop_f_n IS NOT NULL
                           AND abs(temp_pop_f_n - (temp_pop_c_n * 9.0 / 5 + 32)) > 0.5) FROM profile_typed
    UNION ALL SELECT 'hdh_65 < 0',        count(*) FILTER (WHERE hdh_n < 0) FROM profile_typed
    UNION ALL SELECT 'cdh_65 < 0',        count(*) FILTER (WHERE cdh_n < 0) FROM profile_typed
    UNION ALL SELECT 'hdd_65_daily < 0',  count(*) FILTER (WHERE hdd_n < 0) FROM profile_typed
    UNION ALL SELECT 'cdd_65_daily < 0',  count(*) FILTER (WHERE cdd_n < 0) FROM profile_typed
    UNION ALL SELECT 'hour outside 0-23',        count(*) FILTER (WHERE hour_n < 0 OR hour_n > 23) FROM profile_typed
    UNION ALL SELECT 'month outside 1-12',       count(*) FILTER (WHERE month_n < 1 OR month_n > 12) FROM profile_typed
    UNION ALL SELECT 'day_of_week outside 0-6',  count(*) FILTER (WHERE dow_n < 0 OR dow_n > 6) FROM profile_typed
    UNION ALL SELECT 'hour differs from hour of datetime_utc',
        count(*) FILTER (WHERE hour_n IS NOT NULL AND utc_wall IS NOT NULL
                           AND hour_n <> extract(hour FROM utc_wall)) FROM profile_typed
    UNION ALL SELECT 'hour differs from hour of datetime_local',
        count(*) FILTER (WHERE hour_n IS NOT NULL AND local_wall IS NOT NULL
                           AND hour_n <> extract(hour FROM local_wall)) FROM profile_typed
)
SELECT issue, n AS row_count,
       round(100.0 * n / (SELECT count(*) FROM latest_batch), 3) AS pct_of_rows
FROM checks
ORDER BY n DESC, issue;

SELECT j.key AS column_name,
       min(pg_temp.try_float(j.value)) AS min_value,
       max(pg_temp.try_float(j.value)) AS max_value
FROM latest_batch t
     CROSS JOIN LATERAL jsonb_each_text(to_jsonb(t)) j
     JOIN _profile_cols c ON c.col = j.key AND c.kind = 'float'
GROUP BY 1
ORDER BY 1;

SELECT day_of_week, is_weekend, count(*) AS n,
       min(local_date_sample) AS example_local_date
FROM (SELECT day_of_week, is_weekend, left(datetime_local, 10) AS local_date_sample FROM latest_batch) s
GROUP BY 1, 2
ORDER BY 1, 2;


SELECT j.key AS column_name, j.value, count(*) AS n
FROM latest_batch t,
     LATERAL jsonb_each_text(to_jsonb(t)) j
WHERE j.key IN ('hour', 'month', 'day_of_week')
GROUP BY 1, 2
ORDER BY 1, (CASE WHEN j.value ~ '^[0-9]+$' THEN j.value::numeric END), 2;


SELECT 'demand_source' AS column_name, demand_source AS value, count(*) AS n
FROM latest_batch GROUP BY 2
UNION ALL
SELECT 'demand_imputed_pudl_mwh_imputation_code', demand_imputed_pudl_mwh_imputation_code, count(*)
FROM latest_batch GROUP BY 2
ORDER BY 1, 3 DESC;


SELECT j.key AS column_name, count(*) AS values_with_extra_spaces
FROM latest_batch t, LATERAL jsonb_each_text(to_jsonb(t)) j
WHERE left(j.key, 1) <> '_' AND j.value IS NOT NULL AND j.value <> btrim(j.value)
GROUP BY 1
ORDER BY 2 DESC, 1;

SELECT 'datetime_utc' AS column_name,
       regexp_replace(datetime_utc, '[0-9]', '9', 'g') AS shape, count(*) AS n
FROM latest_batch GROUP BY 2
UNION ALL
SELECT 'datetime_local', regexp_replace(datetime_local, '[0-9]', '9', 'g'), count(*)
FROM latest_batch GROUP BY 2
ORDER BY 1, 3 DESC;

SELECT col AS column_name,
       count(*) FILTER (WHERE val IS NOT NULL AND val !~ pat) AS pattern_mismatch,
       count(*) FILTER (WHERE val ~ pat AND parsed IS NULL) AS matches_pattern_but_not_a_real_time
FROM (
    SELECT 'datetime_utc' AS col, datetime_utc AS val, pg_temp.try_ts(datetime_utc) AS parsed,
           '^[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?([+-][0-9]{2}(:?[0-9]{2})?|Z)?$' AS pat
    FROM latest_batch
    UNION ALL
    SELECT 'datetime_local', datetime_local, pg_temp.try_ts(datetime_local),
           '^[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?([+-][0-9]{2}(:?[0-9]{2})?|Z)?$'
    FROM latest_batch
) s
GROUP BY 1
ORDER BY 1;

SELECT (local_wall - utc_wall) AS local_minus_utc, count(*) AS n
FROM profile_typed
WHERE local_wall IS NOT NULL AND utc_wall IS NOT NULL
GROUP BY 1
ORDER BY 1;

WITH d AS (
    SELECT left(datetime_local, 10) AS local_date,
           count(*) AS rows_that_day,
           bool_or(lower(btrim(is_dst_transition_day)) IN ('true', 't', '1', 'yes')) AS flagged_dst
    FROM latest_batch
    WHERE datetime_local ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
    GROUP BY 1
)
SELECT rows_that_day, flagged_dst, count(*) AS n_days, min(local_date) AS first_date, max(local_date) AS last_date
FROM d
GROUP BY 1, 2
ORDER BY 1, 2;

SELECT count(*) AS repeated_datetime_local_values
FROM (SELECT datetime_local FROM latest_batch GROUP BY 1 HAVING count(*) > 1) r;


WITH b AS (
    SELECT min(utc_ts) AS lo, max(utc_ts) AS hi, count(DISTINCT utc_ts) AS actual_hours
    FROM profile_typed
)
SELECT lo AS first_hour, hi AS last_hour,
       (extract(epoch FROM (hi - lo)) / 3600)::bigint + 1 AS expected_hours,
       actual_hours,
       (extract(epoch FROM (hi - lo)) / 3600)::bigint + 1 - actual_hours AS missing_hours
FROM b;

WITH b AS (SELECT min(utc_ts) AS lo, max(utc_ts) AS hi FROM profile_typed)
SELECT g AS missing_hour_utc
FROM b, generate_series(b.lo, b.hi, interval '1 hour') g
EXCEPT
SELECT utc_ts FROM profile_typed
ORDER BY 1
LIMIT 50;

SELECT count(*) AS not_on_the_hour
FROM profile_typed
WHERE utc_ts IS NOT NULL
  AND (extract(minute FROM utc_ts) <> 0 OR extract(second FROM utc_ts) <> 0);

SELECT flag, value, count(*) AS n,
       round(100.0 * count(*) / (SELECT count(*) FROM latest_batch), 3) AS pct_of_rows
FROM (
    SELECT 'demand_is_imputed' AS flag, demand_is_imputed AS value FROM latest_batch
    UNION ALL SELECT 'temp_is_missing',        temp_is_missing        FROM latest_batch
    UNION ALL SELECT 'temp_is_imputed',        temp_is_imputed        FROM latest_batch
    UNION ALL SELECT 'weather_is_preliminary', weather_is_preliminary FROM latest_batch
) f
GROUP BY 1, 2
ORDER BY 1, 2;
