# Latency analysis: PowerSync vs ElectricSQL

## Data and preprocessing

The analysis loaded the newest latency CSV with at least 20 observations for each engine:

- PowerSync: `results/powersync-latency-1791333907825.csv`
- ElectricSQL: `results/electricsql-latency-1791334513081.csv`

The CSV fields were parsed as numeric where appropriate. Rows with missing, duplicated, non-positive, or non-numeric measurements would stop the analysis. The selected files contain 100 PowerSync and 100 ElectricSQL baseline observations, with no validation failures.

## Variables

- **Independent variables:** `engine` (`PowerSync` or `ElectricSQL`) and `network_latency_ms`, the fixed one-way delay added to server-to-client traffic by Toxiproxy.
- **Controlled variables:** database schema, payload pattern, client/server host, Docker configuration, warmup, polling interval, and experiment procedure.
- **Dependent variable:** `latency_ms`, the elapsed time from the Postgres insert timestamp to the timestamp at which the client records the synchronized event. It is expected to be numeric, positive, right-skewable, and independent across event IDs within a run.

## Results by engine and network latency

| engine      |   network_latency_ms |   n |   mean_ms |   std_ms |   median_ms |   min_ms |   p95_ms |   max_ms |   missing_values |   outliers_iqr |
|:------------|---------------------:|----:|----------:|---------:|------------:|---------:|---------:|---------:|-----------------:|---------------:|
| PowerSync   |                    0 | 100 |    47.264 |    4.645 |      46.701 |   39.633 |   53.013 |   68.685 |                0 |              3 |
| PowerSync   |                   25 | 100 |    71.243 |    3.429 |      71.004 |   64.327 |   77.866 |   85.111 |                0 |              5 |
| PowerSync   |                   50 | 100 |    97.988 |    3.386 |      97.573 |   92.005 |  102.727 |  113.671 |                0 |              2 |
| PowerSync   |                  100 | 100 |   146.089 |    4.419 |     145.277 |  137.937 |  153.036 |  171.400 |                0 |              5 |
| ElectricSQL |                    0 | 100 |    16.530 |    2.511 |      16.423 |   11.261 |   19.843 |   31.121 |                0 |              2 |
| ElectricSQL |                   25 | 100 |    43.714 |    2.585 |      43.667 |   37.417 |   46.852 |   57.584 |                0 |              3 |
| ElectricSQL |                   50 | 100 |    69.343 |    1.966 |      69.387 |   64.953 |   71.746 |   80.285 |                0 |              5 |
| ElectricSQL |                  100 | 100 |   121.803 |    2.812 |     121.888 |  116.975 |  124.587 |  142.561 |                0 |              4 |

Each row summarizes one engine and one network latency level. The baseline engine comparison below uses the lowest configured network latency (0 ms). The iteration-to-latency correlations at baseline were:

```text
engine
ElectricSQL   -0.021803
PowerSync     -0.436298
```

The per-level plot shows mean synchronization latency with standard-error bars. The result-file polling interval adds measurement resolution equally across treatment levels when `pollMs` is held constant.

## Research question 1: engine comparison at baseline

The primary comparison is at the lowest configured network delay:

`latency_ms = intercept + engine_effect + error`

With PowerSync as the reference group, the engine effect is the difference between group means. Because the two groups may have different variances, Welch's two-sample t-test is used for the mean difference. The Mann-Whitney U test is included as a distribution-robust comparison of ranks.

- Mean difference, PowerSync minus ElectricSQL: **30.734 ms**
- Bootstrap 95% CI for mean difference: **[29.708, 31.794] ms**
- Welch t-test: **t = 58.206, p = 5.80833e-106**
- Mann-Whitney U test: **U = 10000.0, p = 2.56186e-34**
- Rank-biserial effect size (positive means higher PowerSync latency): **1.000**

Both tests address the narrow question of whether the observed latency distributions differ under this local setup. They do not establish that one technology is universally faster.

## Research question 2: effect of increased network latency

A separate linear trend is estimated for each engine across all configured delay levels:

- **PowerSync:** 0.992 ms additional synchronization latency per 1 ms imposed downstream delay, 95% CI [0.981, 1.003] (R² = 0.988).
- **ElectricSQL:** 1.050 ms additional synchronization latency per 1 ms imposed downstream delay, 95% CI [1.043, 1.057] (R² = 0.996).
- **Slope difference (ElectricSQL minus PowerSync):** 0.058 ms/ms, 95% CI [0.045, 0.070], z = 8.94, p = 3.91e-19.

A positive slope means synchronization latency increased as the imposed server-to-client delay increased. This fixed downstream delay models the path on which synchronized changes reach the client; it is not a general model of Internet conditions.

## Visual aids

- [Baseline latency distributions](latency-distributions.png)
- [Baseline latency by iteration](latency-by-iteration.png)
- [Latency by simulated network latency](latency-by-network-latency.png)
- [Summary table](summary.csv)

## Interpretation and limitations

The comparison is local: each engine uses a separate Postgres and service container, and measurements include synchronization architecture, client processing, polling resolution, and Docker scheduling.

For stronger evidence, repeat each sweep, preserve the same delay levels, warmup, and polling settings, and compare run-level effects in addition to per-event measurements.
