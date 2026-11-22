<!-- Created as fallback for Hisham Wael Hosny; merge/replace if his PR lands. -->

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
