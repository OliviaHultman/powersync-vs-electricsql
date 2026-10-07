# Latency analysis: PowerSync vs ElectricSQL

## Data and preprocessing

The analysis loaded the newest latency CSV file(s) with at least 20 observations for each engine and pooled them when several runs were selected:

- PowerSync: `results/powersync-latency-1791388444691.csv`, `results/powersync-latency-1791388694870.csv`, `results/powersync-latency-1791388945312.csv`
- ElectricSQL: `results/electricsql-latency-1791389196319.csv`, `results/electricsql-latency-1791389431895.csv`, `results/electricsql-latency-1791389667667.csv`

The CSV fields were parsed as numeric where appropriate. Rows with missing, duplicated, non-positive, or non-numeric measurements would stop the analysis. The selected files contain 300 PowerSync and 300 ElectricSQL baseline observations, with no validation failures.

## Variables

- **Independent variables:** `engine` (`PowerSync` or `ElectricSQL`) and `network_latency_ms`, the fixed one-way delay added to server-to-client traffic by Toxiproxy.
- **Controlled variables:** database schema, payload pattern, client/server host, Docker configuration, warmup, polling interval, and experiment procedure.
- **Dependent variable:** `latency_ms`, the elapsed time from the Postgres insert timestamp to the timestamp at which the client records the synchronized event. It is expected to be numeric, positive, right-skewable, and independent across event IDs within a run.

## Results by engine and network latency

| engine      |   network_latency_ms |   n |   mean_ms |   std_ms |   median_ms |   min_ms |   p95_ms |   max_ms |   missing_values |   outliers_iqr |
|:------------|---------------------:|----:|----------:|---------:|------------:|---------:|---------:|---------:|-----------------:|---------------:|
| PowerSync   |                    0 | 300 |    47.380 |    4.337 |      47.000 |       37 |   52.050 |       75 |                0 |             14 |
| PowerSync   |                   25 | 300 |    74.620 |    5.493 |      74.000 |       66 |   79.000 |      113 |                0 |              8 |
| PowerSync   |                   50 | 300 |    99.333 |    2.856 |      99.000 |       90 |  104.000 |      111 |                0 |             13 |
| PowerSync   |                  100 | 300 |   149.920 |    4.701 |     149.000 |      141 |  157.000 |      189 |                0 |             14 |
| ElectricSQL |                    0 | 300 |    17.490 |    2.643 |      17.000 |        9 |   21.000 |       35 |                0 |              6 |
| ElectricSQL |                   25 | 300 |    44.433 |    2.482 |      44.000 |       37 |   47.000 |       58 |                0 |              7 |
| ElectricSQL |                   50 | 300 |    70.420 |    3.057 |      70.000 |       64 |   73.000 |      110 |                0 |              9 |
| ElectricSQL |                  100 | 300 |   122.933 |    2.190 |     123.000 |      114 |  126.000 |      137 |                0 |             12 |

Each row summarizes one engine and one network latency level. The baseline engine comparison below uses the lowest configured network latency (0 ms). The iteration-to-latency correlations at baseline were:

```text
engine
ElectricSQL   -0.013632
PowerSync      0.107022
```

The per-level plot shows the median synchronization latency with a shaded interquartile range (IQR) band. The result-file polling interval adds measurement resolution equally across treatment levels when `pollMs` is held constant.

## Research question 1: engine comparison at baseline

The primary comparison is at the lowest configured network delay:

`latency_ms = intercept + engine_effect + error`

With PowerSync as the reference group, the engine effect is the difference between group means. Because the two groups may have different variances, Welch's two-sample t-test is used for the mean difference. The Mann-Whitney U test is included as a distribution-robust comparison of ranks.

- Mean difference, PowerSync minus ElectricSQL: **29.890 ms**
- Bootstrap 95% CI for mean difference: **[29.327, 30.473] ms**
- Welch t-test: **t = 101.928, p < 0.001**
- Mann-Whitney U test: **U = 90000.0, p < 0.001**
- Rank-biserial effect size (positive means higher PowerSync latency): **1.000**

Both tests address the narrow question of whether the observed latency distributions differ under this local setup. They do not establish that one technology is universally faster.

## Research question 2: effect of increased network latency

A separate linear trend is estimated for each engine across all configured delay levels:

- **PowerSync:** 1.021 ms additional synchronization latency per 1 ms imposed downstream delay, 95% CI [1.014, 1.028] (R² = 0.986).
- **ElectricSQL:** 1.053 ms additional synchronization latency per 1 ms imposed downstream delay, 95% CI [1.049, 1.057] (R² = 0.995).
- **Slope difference (ElectricSQL minus PowerSync):** 0.032 ms/ms, 95% CI [0.024, 0.040], z = 7.88, p < 0.001.

A positive slope means synchronization latency increased as the imposed server-to-client delay increased. This fixed downstream delay models the path on which synchronized changes reach the client; it is not a general model of Internet conditions.

### Run-level consistency

The pooled confidence intervals above treat every measurement as independent. As a run-level check, one slope is fitted per run:

| engine      |   run | level_order_ms   |   slope_ms_per_ms | source_file                           |
|:------------|------:|:-----------------|------------------:|:--------------------------------------|
| PowerSync   |     1 | 0->25->50->100   |             1.016 | powersync-latency-1791388444691.csv   |
| PowerSync   |     2 | 100->50->25->0   |             1.013 | powersync-latency-1791388694870.csv   |
| PowerSync   |     3 | 0->25->50->100   |             1.033 | powersync-latency-1791388945312.csv   |
| ElectricSQL |     1 | 0->25->50->100   |             1.049 | electricsql-latency-1791389196319.csv |
| ElectricSQL |     2 | 100->50->25->0   |             1.053 | electricsql-latency-1791389431895.csv |
| ElectricSQL |     3 | 0->25->50->100   |             1.055 | electricsql-latency-1791389667667.csv |

Every ElectricSQL run had a steeper slope than every PowerSync run.

Median latency per run and delay level (consistency between repeated runs and level orders):

| engine      |   network_latency_ms |   run_1_median_ms |   run_2_median_ms |   run_3_median_ms |
|:------------|---------------------:|------------------:|------------------:|------------------:|
| PowerSync   |                    0 |              46.0 |              47.0 |              47.0 |
| PowerSync   |                   25 |              74.0 |              73.5 |              75.0 |
| PowerSync   |                   50 |              99.0 |              99.0 |             100.0 |
| PowerSync   |                  100 |             148.5 |             149.5 |             150.0 |
| ElectricSQL |                    0 |              17.5 |              17.0 |              18.0 |
| ElectricSQL |                   25 |              44.0 |              45.0 |              44.0 |
| ElectricSQL |                   50 |              70.0 |              71.0 |              70.0 |
| ElectricSQL |                  100 |             123.0 |             123.0 |             124.0 |

## Latency breakdown: delivery and local part

Each latency is split at `notified_at_ms`, the moment the client was told about the change: *delivery* is the time from the insert to the notification, and *local* is the time from the notification until the row was read from the client's SQLite database. Medians of the parts do not necessarily add up exactly to the median of the total.

| engine      |   network_latency_ms |   n |   delivery_median_ms |   local_median_ms |   local_max_ms |   total_median_ms |
|:------------|---------------------:|----:|---------------------:|------------------:|---------------:|------------------:|
| PowerSync   |                    0 | 300 |                 45.0 |               2.0 |              3 |              47.0 |
| PowerSync   |                   25 | 300 |                 72.0 |               2.0 |              3 |              74.0 |
| PowerSync   |                   50 | 300 |                 97.0 |               2.0 |              3 |              99.0 |
| PowerSync   |                  100 | 300 |                147.0 |               2.0 |              4 |             149.0 |
| ElectricSQL |                    0 | 300 |                 11.0 |               6.0 |              8 |              17.0 |
| ElectricSQL |                   25 | 300 |                 38.0 |               6.0 |             10 |              44.0 |
| ElectricSQL |                   50 | 300 |                 64.0 |               6.0 |              8 |              70.0 |
| ElectricSQL |                  100 | 300 |                115.0 |               9.0 |             11 |             123.0 |

The split point is not identical for the two engines. The PowerSync SDK writes the row to SQLite before notifying the client, so that write is part of PowerSync's delivery time, while the ElectricSQL client writes the row itself after being notified, so that write is part of ElectricSQL's local time. Timestamps have 1 ms resolution.

## Visual aids

- [Baseline latency box plot](latency-boxplot.png)
- [Baseline latency histogram](latency-histogram.png)
- [Baseline latency by iteration](latency-by-iteration.png)
- [Latency by simulated network latency](latency-by-network-latency.png)
- [Latency breakdown](latency-breakdown.png)
- [Summary table](summary.csv)
- [Slopes per run](run-slopes.csv)
- [Latency breakdown table](latency-breakdown.csv)

## Interpretation and limitations

The comparison is local: each engine uses a separate Postgres and service container, and measurements include synchronization architecture, client processing, polling resolution, and Docker scheduling.

For stronger evidence, repeat each sweep, preserve the same delay levels, warmup, and polling settings, and compare run-level effects in addition to per-event measurements.
