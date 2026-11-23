# Phase 3: Data Cleaning, Relational Modeling, SQL Analytics, and Data Quality

## Phase scope, deliverables, and status

Phase 3 combines cleaning, relational modeling, analytical SQL, and automated
data quality. Although the repository roadmap labels data quality as Phase 4,
the supplied Phase 3 brief explicitly includes pre-load and post-load checks in
this phase.

| Brief requirement | Implementation and evidence |
|---|---|
| Clean typed data without changing raw data; handle missing values and duplicates; validate required columns and row counts before loading. | `scripts/clean.py` reads one successful raw batch, converts values to typed columns, preserves missing values, removes exact duplicate rows, and rejects conflicting UTC timestamps. `scripts/preload_checks.py` checks the staging columns, data types, and raw-to-clean row count before writing. Raw rows remain in `raw_data`. |
| Design relational tables with keys and constraints, and load reproducibly. | `sql/04_schema_dw.sql` defines the warehouse dimensions and facts; `sql/05_load_dw.sql` fully refreshes them in a deterministic order using UTC timestamps as the stable source key. The grain and key rationale are documented below and in `docs/er_diagram.md`. |
| Use JOINs and analytical views to address project questions. | `sql/06_views_q1.sql`, `sql/07_views_q2.sql`, and `sql/08_views_q3.sql` create six views for the three questions. JOIN keys and reasons are documented in the Q1–Q3 sections below. |
| Run post-load SQL checks and stop on failure. | `scripts/preload_checks.py` defines 19 pre-load checks; `sql/quality_checks.sql` supplies 34 post-load checks to `scripts/run_quality.py`. `scripts/run_pipeline.py` runs them after the warehouse load in the same transaction, rolls back on an exception, skips later stages, and exits nonzero. |
| Demonstrate passing and failing quality cases and document rules, counts, schema, and behavior. | `DATA_QUALITY.md`, `docs/lab_demo_checklist_phase3.md`, `docs/evidence/quality_pass.txt`, and the four `docs/evidence/quality_fail_*.txt` files document the rules and captured outcomes. The pre-load demo is `scripts/demo_preload_fail.py`; the isolated post-load demo is `scripts/demo_quality_fail.py`. |

### Phase execution flow

```text
Kaggle
  -> scripts/extract.py
  -> timestamped original CSV in data/raw/
  -> scripts/ingest.py + scripts/load_raw.py
  -> raw_data.raw_caiso_hourly + raw_data.ingestion_log
  -> scripts/run_pipeline.py
       -> scripts/clean.py: select a successful non-empty batch, type and clean it
       -> scripts/preload_checks.py: validate before any clean/warehouse write
       -> clean_data.stg_caiso_clean
       -> sql/04_schema_dw.sql + sql/05_load_dw.sql
       -> scripts/run_quality.py + sql/quality_checks.sql
       -> commit only after every check passes; otherwise rollback
  -> sql/06_views_q1.sql, sql/07_views_q2.sql, sql/08_views_q3.sql
  -> analytical query results
```

In Compose, `ingest` and `clean` are separate on-demand services. `ingest`
downloads and appends a raw batch; `clean` runs the transactional cleaning and
warehouse pipeline against the latest successful raw batch. Cleaning does not
download data and does not use ingestion's SHA-256 skip behavior. The full
file-by-file guide, including Compose and SQL entry points, is in
[`PROJECT_GUIDE.md`](../PROJECT_GUIDE.md).

### Cleaning behavior and validation boundary

- The raw schema stores all 35 source columns as `TEXT`; cleaning never updates
  or deletes those source values.
- Empty strings are normalized to missing values. UTC and local timestamps,
  numeric values, local calendar integers, and strict `True`/`False` fields
  are parsed into typed values. The local timestamp is converted to
  `America/Los_Angeles` wall-clock time and checked against the source local
  hour and the expected UTC offset.
- Existing NULLs are preserved; the pipeline does not invent replacement
  demand or weather values. Null-share thresholds are enforced by the
  pre-load and post-load checks.
- Exact duplicate rows are removed. A repeated UTC timestamp with conflicting
  content is rejected; it is not silently resolved by choosing one row.
- Unparseable values, invalid booleans, invalid required demand, and invalid
  timestamp relationships raise errors or fail pre-load checks. The current
  implementation rejects these cases rather than applying a guessed repair.
  Since the brief says to "fix invalid values," this is a requirement to
  clarify: either document rejection as the chosen safe handling for invalid
  values or add and test field-specific repair rules before claiming automatic
  correction is implemented.
- For the documented local validation batch `phase3-final-local-seed`, the
  input and cleaned counts were both 98,968; zero exact duplicate rows were
  removed. This batch came from an existing CSV, not a new Kaggle download.

### Checks and evidence boundaries

- Pre-load checks cover required columns, expected dtypes, row-count equality,
  UTC timestamp presence and uniqueness, positive demand, null-share
  thresholds, and calendar/weather ranges (19 checks total). They run before
  staging is written.
- Post-load checks cover primary-key uniqueness, foreign-key integrity, null
  thresholds, numeric/calendar ranges, presence of the source batch, raw to
  clean and warehouse count reconciliation, seven cities, and seven
  city-temperature rows per clean hour (34 checks total).
- A pre-load injected negative demand is exercised in memory, before staging.
  Post-load failure cases corrupt only `dw_test`, an unconstrained copy, so the
  real `dw` tables are not modified.
- The stored quality evidence demonstrates the check runner on an isolated
  two-row warehouse fixture. It demonstrates pass/fail behavior, but by itself
  is not proof that those captured runs used all 98,968 project rows.
- On 2026-11-23, `docker compose run --rm clean` completed successfully against
  the existing raw batch `095e328d2e34`: 98,968 rows before and after cleaning,
  19 pre-load checks passed, 34 post-load checks passed, and the warehouse
  contained 98,968 datetime, demand, and weighted-weather rows plus 692,776
  city-temperature rows. All three view scripts were applied; their six views
  returned rows (21, 21, 1,128, 47, 96, and 7 respectively).
- In the same verification, pre-load and post-load negative-demand demos each
  detected the injected value and exited with code 1. The post-load demo
  removed `dw_test`; a follow-up run confirmed the production warehouse still
  passed all 34 checks and retained the expected row counts.
- This verifies the cleaning, warehouse, views, and quality stages using an
  already-ingested local batch. No new Kaggle request or fresh extract/ingest
  was performed; use the stored raw batch for the offline lab demo.

### Lab/demo readiness

The brief calls for a live pipeline run, database inspection, analytical-view
queries, a passing quality run, and an intentional failing-data demonstration.
The Phase 3 checklist in `docs/lab_demo_checklist_phase3.md` contains commands
and expected results for these steps. Because the evaluation is offline, have a
successful raw batch already in PostgreSQL and confirm that the Compose images
and database are available before the session; do not make a new Kaggle
download a prerequisite for demonstrating cleaning. Show raw/clean/warehouse
counts and PK/FK relationships in `psql` or pgAdmin, apply and query all three
view scripts, run the clean pipeline, then demonstrate pre-load and post-load
failures. Push the scripts, SQL, Compose configuration, and notes before the
evaluation, as required by the brief.

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

**CREATED AS FALLBACK for Hisham:** The local validation batch contained
98,968 raw rows; cleaning retained 98,968 rows and removed no exact duplicates.
The cleaning decisions and row-count table are recorded in
[Cleaning decisions](#cleaning-decisions).

## Q3 views and JOIN justification

### Peak demand by local hour, weekend, and holiday

- Joins: `dw.fact_demand` → `dw.dim_datetime` on `datetime_id`, then `dw.dim_datetime` → `dw.dim_holiday` on `holiday_id`.
- Keys: `dw.fact_demand.datetime_id` and `dw.dim_datetime.datetime_id` identify the hourly fact/dimension row; `dw.dim_datetime.holiday_id` references `dw.dim_holiday.holiday_id`.
- JOIN justification: The inner joins assign each demand row to its local hour, weekend flag, and holiday flag combination through the warehouse keys. `dw.dim_holiday` has no `holiday_date` column, and `sql/08_views_q3.sql` uses no left join.

**CREATED AS FALLBACK for Hisham (real output requested by Fatma's F11b):**
first rows from `dw.v_q3_peak_by_hour_weekend_holiday`, local validation batch
`phase3-final-local-seed`.

| local_hour | is_weekend | is_holiday | avg_demand_mwh | max_demand_mwh |
|---:|:---:|:---:|---:|---:|
| 0 | false | false | 25526.452179557252 | 40644 |
| 0 | false | true | 23925.767123287671 | 36778 |
| 0 | true | false | 25194.907980826326 | 37080 |
| 0 | true | true | 24260.761904761905 | 31003 |
| 1 | false | false | 24020.594803245007 | 37350 |

### City temperature-demand correlation

- Joins: `dw.fact_city_temperature` → `dw.dim_city` on `city_id` and → `dw.fact_demand` on `datetime_id`.
- Keys: `(datetime_id, city_id)` identifies a city temperature fact; `datetime_id` aligns that city temperature with the corresponding hourly demand.
- JOIN justification: The two fact tables share the required hourly grain, and the city dimension supplies the city display name. The view groups on city and ranks absolute Pearson correlation.

**CREATED AS FALLBACK for Hisham (real output requested by Fatma's F11b):**
first rows from `dw.v_q3_city_temp_demand_corr`, local validation batch
`phase3-final-local-seed`.

| city_id | city_name | temperature_demand_corr | correlation_rank |
|---:|---|---:|---:|
| 7 | Fresno | 0.6678662203009746 | 1 |
| 2 | Riverside | 0.6438574194140797 | 2 |
| 6 | Sacramento | 0.6410168506026077 | 3 |
| 1 | Los Angeles | 0.6147983765193056 | 4 |
| 3 | San Diego | 0.5899700863232336 | 5 |

### Cleaning decisions

The profiling values below are from profiled batch `48e7a1d23f5a`, as recorded in
[`phase2_profiling_details.md`](./phase2_profiling_details.md) (§§3.1–3.5).
The local validation clean run used batch `phase3-final-local-seed`.

| Issue found in profiling | Decision | Before → after |
|---|---|---|
| 35 raw source columns are TEXT | Parse timestamps, numbers, booleans, and local calendar integers into typed values in clean staging; raw stays unchanged. | 35 TEXT source columns → typed values (profiling details §2) |
| Imputation-code NULLs | Keep NULLs; do not infer missing demand from the code field. | 98,397 NULLs → 98,397 NULLs (profiling details §3.2) |
| `demand_imputed_pudl_mwh` NULLs | Keep NULLs; do not impute in cleaning. | 928 → 928 NULLs (profiling details §3.2) |
| `demand_reported_mwh` NULLs | Keep NULLs; do not impute in cleaning. | 426 → 426 NULLs (profiling details §3.2) |
| `hdd_65_daily` / `cdd_65_daily` NULLs | Keep NULLs; do not impute in cleaning. | 40 / 40 → 40 / 40 NULLs (profiling details §3.2) |
| `hour` differs from the UTC clock but matches local clock | Treat `hour` as local hour; use UTC timestamp as the stable time key. | 98,968 UTC-hour mismatches; 0 local-hour mismatches (profiling details §3.1) |
| `demand_reported_mwh` has a low minimum | Keep the 14 MWh observation and flag it for investigation; do not filter it. | 14 MWh vs. 14,372 MWh minimum in other demand fields (profiling details §3.5) |
| Duplicate UTC timestamps | Reject conflicting duplicate keys; no duplicate timestamp groups were profiled. | 0 duplicate groups (profiling details §3.1) |
| Partial first/last local dates and DST-length dates | Preserve source coverage; do not pad partial or 23/25-hour dates. | Edge dates: 23 and 17 rows; DST dates: 11 with 23 and 11 with 25 rows (profiling details §3.4) |
| Imputation and preliminary-weather flags | Preserve flags as metadata; do not treat them as failures or impute them away. | 571 imputed-demand flags; 1,947 preliminary-weather flags (profiling details §3.5) |

#### Before/after row counts

**CREATED AS FALLBACK for Hisham:** These observed counts are from local
validation batch `phase3-final-local-seed`, loaded from an existing CSV rather than
a new Kaggle ingestion run.

| Measure | Before cleaning (raw batch) | After cleaning | Difference |
|---|---:|---:|---:|
| Rows | 98,968 | 98,968 | 0 |

## Q1 views and JOIN justification

**CREATED AS FALLBACK for Hisham; Q1 view documentation requested by Zeyad.**

- `dw.v_q1_demand_by_temp_bin` joins `dw.fact_demand` to
  `dw.fact_weather_weighted` on `datetime_id`, then joins
  `dw.dim_datetime` on the same key. Both facts have one row per datetime;
  the joins align each demand observation with its weather and canonical
  datetime row. The view bins non-NULL `temp_pop_wt_c` values with
  `FLOOR(temp_pop_wt_c / 2.0) * 2`, then reports hourly row count, average
  demand, and sample standard deviation for each 2-degree Celsius bin.
- `dw.v_q1_demand_slope` reads the binned view, orders bins by their lower
  temperature bound, and uses `LAG(avg_demand_mwh)` to report the previous
  bin's average and the change from that average. This makes temperature
  intervals where demand begins increasing visible.
- The views were queried against the 98,968-row local validation batch
  `phase3-final-local-seed`, loaded from an existing CSV; this was not a new Kaggle
  ingestion run.

First rows from `dw.v_q1_demand_by_temp_bin`:

| temp_bin_c | hours_count | avg_demand_mwh | stddev_demand_mwh |
|---:|---:|---:|---:|
| 2 | 131 | 22849.833522448625 | 1809.527824625498 |
| 4 | 705 | 22701.634042553191 | 1780.560597683010 |
| 6 | 2296 | 22425.476490671032 | 2137.260735643377 |
| 8 | 4818 | 22646.941021397257 | 2599.571797385675 |
| 10 | 7708 | 22942.650016488034 | 2808.615501397326 |

First rows from `dw.v_q1_demand_slope`:

| temp_bin_c | previous_bin_avg_demand_mwh | demand_increase_from_previous_bin_mwh |
|---:|---:|---:|
| 2 | NULL | NULL |
| 4 | 22849.833522448625 | -148.199479895434 |
| 6 | 22701.634042553191 | -276.157551882159 |
| 8 | 22425.476490671032 | 221.464530726225 |
| 10 | 22646.941021397257 | 295.708995090777 |

In this result, average demand first increases between the 6-degree and
8-degree bins (+221.465 MWh); it increases by a further 295.709 MWh in the
10-degree bin. These are descriptive bin-to-bin changes, not a causal
temperature estimate.

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

**CREATED AS FALLBACK for Hisham:** real first rows from both Q2 views,
local validation batch `phase3-final-local-seed`.

| year | season | local_hour | avg_demand_mwh | avg_shortwave_radiation_pop_wt_wm2 | avg_cloud_cover_pop_wt_pct |
|---:|---|---:|---:|---:|---:|
| 2015 | fall | 0 | 26854.472527472527 | 0 | 25.1558511853295586 |
| 2015 | fall | 1 | 24713.826086956522 | 0 | 26.9239876824534399 |
| 2015 | fall | 2 | 23364.395604395604 | 0 | 29.9578563779618531 |
| 2015 | fall | 3 | 22460.362637362637 | 0 | 36.4625962651957566 |
| 2015 | fall | 4 | 21845.538461538462 | 0 | 35.6904750263686385 |

| year | season | midday_avg_demand_mwh | evening_ramp_avg_demand_mwh | midday_dip_mwh |
|---:|---|---:|---:|---:|
| 2015 | fall | 28004.096153846154 | 31577.589743589744 | 3573.493589743590 |
| 2015 | summer | 31451.802419354839 | 37048.322580645161 | 5596.520161290322 |
| 2015 | winter | 25626.677419354839 | 26935.924731182796 | 1309.247311827957 |
| 2016 | fall | 26895.724957380081 | 29958.019333529819 | 3062.294376149738 |
| 2016 | spring | 25354.347826086957 | 26102.105072463768 | 747.757246376811 |

Rerun the views with:

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
associated values were queried from clean staging for local validation batch
`phase3-final-local-seed`. The observation is retained, not filtered:

| datetime_utc | demand_reported_mwh | demand_mwh | demand_imputed_pudl_mwh | demand_source | demand_imputed_pudl_mwh_imputation_code |
|---|---:|---:|---:|---|---|
| 2019-12-20 00:00:00+00 | 14.0 | 24682.494335687497 | 24682.494335687497 | pudl | local_outlier_low |

Query every row at the observed minimum; this does not remove or alter any data:

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
