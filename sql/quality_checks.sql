-- The runner replaces {schema} with a safely quoted schema identifier.
-- Every row returned is (check_name, failed_rows, detail); zero passes.
WITH latest_success AS (
    SELECT log.batch_id
    FROM raw_data.ingestion_log AS log
    WHERE log.status = 'SUCCESS'
      AND EXISTS (
          SELECT 1
          FROM raw_data.raw_caiso_hourly AS raw
          WHERE raw._batch_id = log.batch_id
      )
    ORDER BY log.finished_at DESC NULLS LAST,
             log.started_at DESC NULLS LAST,
             log.batch_id DESC
    LIMIT 1
),
raw_count AS (
    SELECT COUNT(raw._batch_id)::BIGINT AS row_count
    FROM latest_success AS latest
    LEFT JOIN raw_data.raw_caiso_hourly AS raw
        ON raw._batch_id = latest.batch_id
),
clean_count AS (
    SELECT COUNT(*)::BIGINT AS row_count
    FROM clean_data.stg_caiso_clean
),
null_metrics AS (
    SELECT
        'demand_reported_null_pct'::TEXT AS check_name,
        COUNT(*)::BIGINT AS total_rows,
        COUNT(*) FILTER (WHERE demand_reported_mwh IS NULL)::BIGINT
            AS null_rows,
        1.0::NUMERIC AS max_pct
    FROM {schema}.fact_demand
    UNION ALL
    SELECT
        'demand_imputed_null_pct',
        COUNT(*)::BIGINT,
        COUNT(*) FILTER (WHERE demand_imputed_pudl_mwh IS NULL)::BIGINT,
        2.0::NUMERIC
    FROM {schema}.fact_demand
    UNION ALL
    SELECT
        'hdd_daily_null_pct',
        COUNT(*)::BIGINT,
        COUNT(*) FILTER (WHERE hdd_65_daily IS NULL)::BIGINT,
        0.1::NUMERIC
    FROM {schema}.fact_weather_weighted
    UNION ALL
    SELECT
        'cdd_daily_null_pct',
        COUNT(*)::BIGINT,
        COUNT(*) FILTER (WHERE cdd_65_daily IS NULL)::BIGINT,
        0.1::NUMERIC
    FROM {schema}.fact_weather_weighted
),
checks AS (
    SELECT
        'dim_holiday_pk'::TEXT AS check_name,
        COUNT(*) - COUNT(DISTINCT holiday_id) AS failed_rows,
        FORMAT(
            'rows=%s, distinct_keys=%s',
            COUNT(*),
            COUNT(DISTINCT holiday_id)
        ) AS detail
    FROM {schema}.dim_holiday
    UNION ALL
    SELECT
        'dim_datetime_pk',
        COUNT(*) - COUNT(DISTINCT datetime_id),
        FORMAT('rows=%s, distinct_keys=%s', COUNT(*), COUNT(DISTINCT datetime_id))
    FROM {schema}.dim_datetime
    UNION ALL
    SELECT
        'datetime_utc_not_null',
        COUNT(*) FILTER (WHERE datetime_utc IS NULL)::BIGINT,
        FORMAT(
            'NULL datetime_utc values=%s',
            COUNT(*) FILTER (WHERE datetime_utc IS NULL)
        )
    FROM {schema}.dim_datetime
    UNION ALL
    SELECT
        'datetime_utc_unique',
        COUNT(*) - COUNT(DISTINCT datetime_utc),
        FORMAT(
            'rows=%s, distinct_datetime_utc=%s',
            COUNT(*),
            COUNT(DISTINCT datetime_utc)
        )
    FROM {schema}.dim_datetime
    UNION ALL
    SELECT
        'dim_city_pk',
        COUNT(*) - COUNT(DISTINCT city_id),
        FORMAT('rows=%s, distinct_keys=%s', COUNT(*), COUNT(DISTINCT city_id))
    FROM {schema}.dim_city
    UNION ALL
    SELECT
        'fact_demand_pk',
        COUNT(*) - COUNT(DISTINCT datetime_id),
        FORMAT('rows=%s, distinct_keys=%s', COUNT(*), COUNT(DISTINCT datetime_id))
    FROM {schema}.fact_demand
    UNION ALL
    SELECT
        'fact_weather_weighted_pk',
        COUNT(*) - COUNT(DISTINCT datetime_id),
        FORMAT('rows=%s, distinct_keys=%s', COUNT(*), COUNT(DISTINCT datetime_id))
    FROM {schema}.fact_weather_weighted
    UNION ALL
    SELECT
        'fact_city_temperature_pk',
        COUNT(*) - COUNT(DISTINCT (datetime_id, city_id)),
        FORMAT(
            'rows=%s, distinct_keys=%s',
            COUNT(*),
            COUNT(DISTINCT (datetime_id, city_id))
        )
    FROM {schema}.fact_city_temperature

    UNION ALL
    SELECT
        'datetime_holiday_fk',
        COUNT(*)::BIGINT,
        FORMAT('orphan rows=%s', COUNT(*))
    FROM {schema}.dim_datetime AS dt
    LEFT JOIN {schema}.dim_holiday AS holiday
        ON holiday.holiday_id = dt.holiday_id
    WHERE holiday.holiday_id IS NULL
    UNION ALL
    SELECT
        'demand_datetime_fk',
        COUNT(*)::BIGINT,
        FORMAT('orphan rows=%s', COUNT(*))
    FROM {schema}.fact_demand AS demand
    LEFT JOIN {schema}.dim_datetime AS dt
        ON dt.datetime_id = demand.datetime_id
    WHERE dt.datetime_id IS NULL
    UNION ALL
    SELECT
        'weather_datetime_fk',
        COUNT(*)::BIGINT,
        FORMAT('orphan rows=%s', COUNT(*))
    FROM {schema}.fact_weather_weighted AS weather
    LEFT JOIN {schema}.dim_datetime AS dt
        ON dt.datetime_id = weather.datetime_id
    WHERE dt.datetime_id IS NULL
    UNION ALL
    SELECT
        'city_temperature_datetime_fk',
        COUNT(*)::BIGINT,
        FORMAT('orphan rows=%s', COUNT(*))
    FROM {schema}.fact_city_temperature AS temperature
    LEFT JOIN {schema}.dim_datetime AS dt
        ON dt.datetime_id = temperature.datetime_id
    WHERE dt.datetime_id IS NULL
    UNION ALL
    SELECT
        'city_temperature_city_fk',
        COUNT(*)::BIGINT,
        FORMAT('orphan rows=%s', COUNT(*))
    FROM {schema}.fact_city_temperature AS temperature
    LEFT JOIN {schema}.dim_city AS city
        ON city.city_id = temperature.city_id
    WHERE city.city_id IS NULL

    UNION ALL
    SELECT
        check_name,
        CASE
            WHEN total_rows > 0
             AND 100.0 * null_rows / total_rows > max_pct
                THEN null_rows
            ELSE 0::BIGINT
        END AS failed_rows,
        FORMAT(
            'nulls=%s/%s (%s%%); maximum=%s%%',
            null_rows,
            total_rows,
            ROUND(
                COALESCE(100.0 * null_rows / NULLIF(total_rows, 0), 0),
                4
            ),
            max_pct
        ) AS detail
    FROM null_metrics

    UNION ALL
    SELECT
        'latest_success_batch_exists',
        CASE
            WHEN EXISTS (SELECT 1 FROM latest_success) THEN 0::BIGINT
            ELSE 1::BIGINT
        END,
        CASE
            WHEN EXISTS (SELECT 1 FROM latest_success)
                THEN 'latest SUCCESS batch with raw rows found'
            ELSE 'no SUCCESS batch with raw rows exists'
        END
    UNION ALL
    SELECT
        'demand_mwh_positive',
        COUNT(*)::BIGINT,
        FORMAT('NULL or non-positive demand rows=%s', COUNT(*))
    FROM {schema}.fact_demand
    WHERE demand_mwh IS NULL OR demand_mwh <= 0
    UNION ALL
    SELECT
        'cloud_cover_range',
        COUNT(*)::BIGINT,
        FORMAT('values outside 0-100=%s', COUNT(*))
    FROM {schema}.fact_weather_weighted
    WHERE cloud_cover_pop_wt_pct < 0 OR cloud_cover_pop_wt_pct > 100
    UNION ALL
    SELECT
        'shortwave_radiation_non_negative',
        COUNT(*)::BIGINT,
        FORMAT('negative values=%s', COUNT(*))
    FROM {schema}.fact_weather_weighted
    WHERE shortwave_radiation_pop_wt_wm2 < 0
    UNION ALL
    SELECT
        'hdh_65_non_negative',
        COUNT(*)::BIGINT,
        FORMAT('negative values=%s', COUNT(*))
    FROM {schema}.fact_weather_weighted
    WHERE hdh_65 < 0
    UNION ALL
    SELECT
        'cdh_65_non_negative',
        COUNT(*)::BIGINT,
        FORMAT('negative values=%s', COUNT(*))
    FROM {schema}.fact_weather_weighted
    WHERE cdh_65 < 0
    UNION ALL
    SELECT
        'hdd_65_daily_non_negative',
        COUNT(*)::BIGINT,
        FORMAT('negative values=%s', COUNT(*))
    FROM {schema}.fact_weather_weighted
    WHERE hdd_65_daily < 0
    UNION ALL
    SELECT
        'cdd_65_daily_non_negative',
        COUNT(*)::BIGINT,
        FORMAT('negative values=%s', COUNT(*))
    FROM {schema}.fact_weather_weighted
    WHERE cdd_65_daily < 0
    UNION ALL
    SELECT
        'datetime_month_range',
        COUNT(*)::BIGINT,
        FORMAT('values outside 1-12=%s', COUNT(*))
    FROM {schema}.dim_datetime
    WHERE month NOT BETWEEN 1 AND 12
    UNION ALL
    SELECT
        'datetime_hour_range',
        COUNT(*)::BIGINT,
        FORMAT('values outside 0-23=%s', COUNT(*))
    FROM {schema}.dim_datetime
    WHERE hour NOT BETWEEN 0 AND 23
    UNION ALL
    SELECT
        'datetime_day_of_week_range',
        COUNT(*)::BIGINT,
        FORMAT('values outside 0-6=%s', COUNT(*))
    FROM {schema}.dim_datetime
    WHERE day_of_week NOT BETWEEN 0 AND 6

    UNION ALL
    SELECT
        'raw_batch_vs_clean',
        ABS((SELECT row_count FROM raw_count)
            - (SELECT row_count FROM clean_count)),
        FORMAT(
            'latest SUCCESS batch raw rows=%s; clean rows=%s',
            (SELECT row_count FROM raw_count),
            (SELECT row_count FROM clean_count)
        )
    UNION ALL
    SELECT
        'raw_batch_vs_dim_datetime',
        ABS((SELECT row_count FROM raw_count)
            - (SELECT COUNT(*) FROM {schema}.dim_datetime)),
        FORMAT(
            'latest SUCCESS batch raw rows=%s; dim_datetime rows=%s',
            (SELECT row_count FROM raw_count),
            (SELECT COUNT(*) FROM {schema}.dim_datetime)
        )
    UNION ALL
    SELECT
        'raw_batch_vs_fact_demand',
        ABS((SELECT row_count FROM raw_count)
            - (SELECT COUNT(*) FROM {schema}.fact_demand)),
        FORMAT(
            'latest SUCCESS batch raw rows=%s; fact_demand rows=%s',
            (SELECT row_count FROM raw_count),
            (SELECT COUNT(*) FROM {schema}.fact_demand)
        )
    UNION ALL
    SELECT
        'raw_batch_vs_fact_weather_weighted',
        ABS((SELECT row_count FROM raw_count)
            - (SELECT COUNT(*) FROM {schema}.fact_weather_weighted)),
        FORMAT(
            'latest SUCCESS batch raw rows=%s; fact_weather_weighted rows=%s',
            (SELECT row_count FROM raw_count),
            (SELECT COUNT(*) FROM {schema}.fact_weather_weighted)
        )
    UNION ALL
    SELECT
        'dim_city_count',
        ABS(COUNT(*) - 7),
        FORMAT('dim_city rows=%s; expected=7', COUNT(*))
    FROM {schema}.dim_city
    UNION ALL
    SELECT
        'fact_city_temperature_vs_clean',
        ABS(
            (SELECT COUNT(*) FROM {schema}.fact_city_temperature)
            - 7 * (SELECT row_count FROM clean_count)
        ),
        FORMAT(
            'fact_city_temperature rows=%s; clean rows=%s; expected=%s',
            (SELECT COUNT(*) FROM {schema}.fact_city_temperature),
            (SELECT row_count FROM clean_count),
            7 * (SELECT row_count FROM clean_count)
        )
)
SELECT check_name, failed_rows, detail
FROM checks
ORDER BY check_name;
