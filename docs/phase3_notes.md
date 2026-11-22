<!-- Created as fallback for Hisham Wael Hosny; merge/replace if his PR lands. -->

## Schema: Basel

### Schema justification

The warehouse is a star schema: `dim_datetime`, `dim_holiday`, and `dim_city` hold reusable descriptive attributes, while the fact tables hold numeric measures at explicit grains. This separates filtering/grouping attributes from measures and lets the hourly demand/weather facts share a stable time dimension.

- `fact_demand` grain: one row per UTC hour (`datetime_id`); `demand_mwh` is required and must be positive.
- `fact_weather_weighted` grain: one row per UTC hour (`datetime_id`), containing population-weighted weather and degree-hour/day measures.
- `fact_city_temperature` grain: one row per UTC hour and city (`datetime_id`, `city_id`). The long shape makes city a relational key, enabling consistent per-city joins, grouping, and correlation without seven city-specific columns.
- `dim_datetime.datetime_id` is reproducible: a full refresh assigns `ROW_NUMBER()` ordered by unique `datetime_utc`. `datetime_utc` is also unique and is the stable source key. `year`, `month`, and `season` are derived from local datetime. Seasons are meteorological: winter Dec-Feb, spring Mar-May, summer Jun-Aug, fall Sep-Nov.
- `dim_holiday` is a small lookup/junk dimension of the distinct four-flag combinations (statutory, observed, California statutory, California observed). Its `holiday_id` is the primary key and the flag combination is unique; `dim_datetime.holiday_id` references it. This keeps the flags represented once per combination while giving each datetime a single required classification.
- `dim_city` contains the seven source cities. No `population_weight` column is included because the input does not provide city-level weights and no published weight source is cited here.
- Foreign keys enforce valid dimension references; primary/unique keys enforce each table's grain and stable keys. Checks constrain month, local hour, weekday, demand, cloud cover, radiation, and heating/cooling degree measures to the required ranges.
- Indexes support the holiday and datetime filters and fact-to-dimension joins, including city lookup for long-form temperatures.
- The load truncates facts before dimensions and inserts dimensions before facts. This full refresh avoids stale dimensions or mixed batches, and deterministic datetime IDs make a rebuild stable. It runs in the caller's transaction, so any failure can roll back the entire refresh.

The regenerable entity relationship diagram is in [docs/er_diagram.md](./er_diagram.md); its PNG companion is [docs/er_diagram.png](./er_diagram.png).

## Hisham notes

<!-- This skeleton is for Hisham's Phase 3 notes. -->

## Q3 views and JOIN justification

### Peak demand by local hour, weekend, and holiday

- Joins: `dw.fact_demand` → `dw.dim_datetime` on `datetime_utc`; left-joins `dw.dim_holiday` on `dim_holiday.holiday_date = DATE(dim_datetime.datetime_local)`.
- Keys: `fact_demand.datetime_utc` and `dim_datetime.datetime_utc` are the fact/dimension key; `dim_holiday.holiday_date` is the holiday date key.
- JOIN justification: The datetime join assigns each demand value to its local hour/weekend attributes. The left join adds an optional holiday flag without dropping hours or demand rows that have no holiday match.
- Real first rows:
  ```text
  local_hour | is_weekend | is_holiday | avg_demand_mwh       | max_demand_mwh
  0          | false      | false      | 25447.097334662393   | 40644.0
  0          | true       | false      | 25178.255122084940   | 37080.0
  1          | false      | false      | 23955.706533973530   | 37350.0
  1          | true       | false      | 23762.908364928987   | 34241.0
  ```
  The real view contains 24 distinct local hours and 48 hour/weekend/holiday groups.

### City temperature-demand correlation

- Joins: `dw.fact_city_temperature` → `dw.dim_city` on `city_id` and → `dw.fact_demand` on `datetime_utc`.
- Keys: `(datetime_utc, city_id)` identifies a city temperature fact; `datetime_utc` connects it to demand.
- JOIN justification: Both the city temperature and demand facts use `datetime_utc`, so joining on that key aligns each city's temperature with the corresponding hourly demand. The city dimension supplies the display name.
- Real first rows:
  ```text
  city_id | city_name     | temperature_demand_corr | correlation_rank
  7       | Fresno        | 0.6678662203009756      | 1
  2       | Riverside     | 0.6438574194140775      | 2
  6       | Sacramento    | 0.6410168506026087      | 3
  1       | Los Angeles   | 0.6147983765193046      | 4
  ```
  The real view contains 7 city rows. Fresno has rank 1.

### Cleaning decisions

The profiling values below are from batch `48e7a1d23f5a`, as recorded in
[`phase2_profiling_details.md`](./phase2_profiling_details.md) (§§3.1–3.5).
The cleaning-run row counts are from batch `phase3_hisham_audit`; the existing
console capture records the selected batch and the `clean.py` before/after
line in [`logs/preload_pass.log`](./logs/preload_pass.log:2). Cleaned NULL
counts appear on lines 14–18, and the preserved flag counts on line 39.

| Issue found in profiling | Decision | Before → after |
|---|---|---|
| 35 raw source columns are TEXT | Parse timestamps, numbers, booleans, and local calendar integers into typed values in clean staging; raw stays unchanged. | 35 TEXT source columns → typed values (profiling details §2; clean log line 5) |
| Imputation-code NULLs | Keep NULLs; do not infer missing demand from the code field. | 98,397 NULLs → 98,397 NULLs (profiling details §3.2; clean log line 16) |
| `demand_imputed_pudl_mwh` NULLs | Keep NULLs; do not impute in cleaning. | 928 → 928 NULLs (profiling details §3.2; clean log line 15) |
| `demand_reported_mwh` NULLs | Keep NULLs; do not impute in cleaning. | 426 → 426 NULLs (profiling details §3.2; clean log line 14) |
| `hdd_65_daily` / `cdd_65_daily` NULLs | Keep NULLs; do not impute in cleaning. | 40 / 40 → 40 / 40 NULLs (profiling details §3.2; clean log lines 17–18) |
| `hour` differs from the UTC clock but matches local clock | Treat `hour` as local hour; use UTC timestamp as the stable time key. | 98,968 UTC-hour mismatches; 0 local-hour mismatches (profiling details §3.1) |
| `demand_reported_mwh` has a low minimum | Keep the 14 MWh observation and flag it for investigation; do not filter it. | 14 MWh vs. 14,372 MWh minimum in other demand fields (profiling details §3.5) |
| Duplicate UTC timestamps | Reject conflicting duplicate keys; no duplicate timestamp groups were profiled, and no exact duplicates were removed in the cited clean run. | 0 duplicate groups; 0 removed (profiling details §3.1; `preload_pass.log`, clean.py line 8) |
| Partial first/last local dates and DST-length dates | Preserve source coverage; do not pad partial or 23/25-hour dates. | Edge dates: 23 and 17 rows; DST dates: 11 with 23 and 11 with 25 rows (profiling details §3.4) |
| Imputation and preliminary-weather flags | Preserve flags as metadata; do not treat them as failures or impute them away. | 571 imputed-demand flags; 1,947 preliminary-weather flags (profiling details §3.5; clean log line 39) |

#### Before/after row counts

| Batch | Raw batch rows | Clean rows | Removed |
|---|---:|---:|---:|
| `phase3_hisham_audit` | 98,968 | 98,968 | 0 |

The row counts and zero-removal result come from `clean.py` output for the
selected batch (`preload_pass.log`, lines 2 and 7–8). These are a saved
pre-existing console capture, not a run performed during this audit.

### Q2 views and JOIN justification

- `dw.v_q2_load_shape_by_year_season_hour` joins `dw.fact_demand`,
  `dw.fact_weather_weighted`, and `dw.dim_datetime` on their shared
  `datetime_id`. The two fact tables each have one row per datetime, so inner
  joins align demand with its corresponding weighted solar/cloud measures;
  the datetime dimension supplies year, meteorological season, and local hour.
- `dw.v_q2_midday_dip` uses the same tables and `datetime_id` joins. Its
  definition is average demand at local hours 17–19 minus average demand at
  local hours 11–14. A larger positive value means a deeper midday dip
  relative to the evening ramp.
- Seasons follow `dw.dim_datetime` in `sql/05_load_dw.sql`: meteorological
  seasons derived from local month (winter Dec–Feb, spring Mar–May, summer
  Jun–Aug, fall Sep–Nov).
- **Real first rows:** NOT EXECUTED in this audit. No database was running and
  there was no listener on port 5432; no result rows are claimed here. Once the
  views are loaded, run:

  ```sql
  SELECT * FROM dw.v_q2_load_shape_by_year_season_hour
  ORDER BY year, season, local_hour
  LIMIT 5;

  SELECT * FROM dw.v_q2_midday_dip
  ORDER BY year, season
  LIMIT 5;
  ```

### Low reported-demand observation

The profiled minimum is 14 MWh versus 14,372 MWh for the other demand fields
(`phase2_profiling_details.md`, §3.5). The real affected timestamps and
associated values were **NOT EXECUTED / not available** during this audit
because PostgreSQL was not running. Query every row at the observed minimum
after the database is available; this does not remove or alter any data:

```sql
SELECT
    datetime_utc,
    demand_reported_mwh,
    demand_mwh,
    demand_imputed_pudl_mwh,
    demand_source,
    demand_imputed_pudl_mwh_imputation_code
FROM clean_data.stg_caiso_clean
WHERE demand_reported_mwh = 14
ORDER BY datetime_utc;
```
