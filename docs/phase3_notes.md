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

### Cleaning summary and counts (Hisham)
- Raw rows: 98,968 | Clean rows: 98,968 | Removed: 0 (based on the latest SUCCESS batch in raw_data.ingestion_log and full-refresh rebuilds).
- All 35 raw columns start as TEXT: trim spaces, convert empty strings to NULL, and cast strictly to target types (UTC timestamp, local timestamp, numbers, booleans) so bad values fail early.
- Kept NULLs as-is without guessing or imputing:
  - demand_imputed_pudl_mwh_imputation_code: 98,397 missing (99.423%)
  - demand_imputed_pudl_mwh: 928 missing (0.938%)
  - demand_reported_mwh: 426 missing (0.430%)
  - hdd_65_daily and cdd_65_daily: 40 missing each (0.040%)
- Deduplication checks datetime_utc (0 exact duplicates removed; conflicting rows fail). Partial boundary/DST day counts and local hour are kept as-is, and the 14 MWh minimum in demand_reported_mwh is noted as an observation rather than dropped automatically.
