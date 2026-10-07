# Latency analysis: PowerSync vs ElectricSQL

## Data and preprocessing

The analysis loaded the newest latency CSV file(s) with at least 20 observations for each engine and pooled them when several runs were selected:

- PowerSync: `results/powersync-latency-1791388945312.csv`, `results/powersync-latency-1791388694870.csv`, `results/powersync-latency-1791388444691.csv`
- ElectricSQL: `results/electricsql-latency-1791389667667.csv`, `results/electricsql-latency-1791389431895.csv`, `results/electricsql-latency-1791389196319.csv`

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

The per-level plot shows mean synchronization latency with standard-error bars. The result-file polling interval adds measurement resolution equally across treatment levels when `pollMs` is held constant.

## Research question 1: engine comparison at baseline

The primary comparison is at the lowest configured network delay:

`latency_ms = intercept + engine_effect + error`

With PowerSync as the reference group, the engine effect is the difference between group means. Because the two groups may have different variances, Welch's two-sample t-test is used for the mean difference. The Mann-Whitney U test is included as a distribution-robust comparison of ranks.

- Mean difference, PowerSync minus ElectricSQL: **29.890 ms**
- Bootstrap 95% CI for mean difference: **[29.323, 30.467] ms**
- Welch t-test: **t = 101.928, p = 0**
- Mann-Whitney U test: **U = 90000.0, p = 4.53764e-100**
- Rank-biserial effect size (positive means higher PowerSync latency): **1.000**

Both tests address the narrow question of whether the observed latency distributions differ under this local setup. They do not establish that one technology is universally faster.

## Research question 2: effect of increased network latency

A separate linear trend is estimated for each engine across all configured delay levels:

- **PowerSync:** 1.021 ms additional synchronization latency per 1 ms imposed downstream delay, 95% CI [1.014, 1.028] (R² = 0.986).
- **ElectricSQL:** 1.053 ms additional synchronization latency per 1 ms imposed downstream delay, 95% CI [1.049, 1.057] (R² = 0.995).
- **Slope difference (ElectricSQL minus PowerSync):** 0.032 ms/ms, 95% CI [0.024, 0.040], z = 7.88, p = 3.26e-15.

A positive slope means synchronization latency increased as the imposed server-to-client delay increased. This fixed downstream delay models the path on which synchronized changes reach the client; it is not a general model of Internet conditions.

## Visual aids

- [Baseline latency distributions](latency-distributions.png)
- [Baseline latency by iteration](latency-by-iteration.png)
- [Latency by simulated network latency](latency-by-network-latency.png)
- [Summary table](summary.csv)

## Interpretation and limitations

The comparison is local: each engine uses a separate Postgres and service container, and measurements include synchronization architecture, client processing, polling resolution, and Docker scheduling.

For stronger evidence, repeat each sweep, preserve the same delay levels, warmup, and polling settings, and compare run-level effects in addition to per-event measurements.
