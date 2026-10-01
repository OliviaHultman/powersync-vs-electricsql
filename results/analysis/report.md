# Latency analysis: PowerSync vs ElectricSQL

## Data and preprocessing

The analysis loaded the newest latency CSV with at least 20 observations for each engine:

- PowerSync: `results/powersync-latency-1790845451144.csv`
- ElectricSQL: `results/electricsql-latency-1790845542098.csv`

The CSV fields were parsed as numeric where appropriate. Rows with missing, duplicated, non-positive, or non-numeric measurements would stop the analysis. The selected files contain 100 PowerSync and 100 ElectricSQL observations, with no validation failures.

## Variables

- **Independent variable:** `engine`, a categorical two-level factor (`PowerSync` or `ElectricSQL`). The experiment holds the database schema, payload pattern, iteration count, client machine, and orchestrator procedure constant.
- **Controlled variables:** `iteration`, `delayMs`, client/server host, Docker configuration, and experiment code. `iteration` is an ordering variable, not a causal treatment.
- **Dependent variable:** `latency_ms`, the elapsed time from the Postgres insert timestamp to the timestamp at which the client records the synchronized event. It is expected to be numeric, positive, right-skewable, and independent across event IDs within a run.

## Exploratory data analysis

| engine      |   n |   mean_ms |   std_ms |   median_ms |   min_ms |   p95_ms |   max_ms |   missing_values |   outliers_iqr |
|:------------|----:|----------:|---------:|------------:|---------:|---------:|---------:|-----------------:|---------------:|
| PowerSync   | 100 |    72.025 |    2.568 |      71.907 |   64.581 |   75.151 |   84.115 |                0 |              4 |
| ElectricSQL | 100 |    15.887 |    2.072 |      15.929 |   11.273 |   19.096 |   23.801 |                0 |              1 |

The latency measurements are positive and complete. The iteration-to-latency correlations were:

```text
engine
ElectricSQL   -0.088756
PowerSync     -0.104318
```

The figures show the group distributions, outliers, and whether latency drifts over the run. The p95 is close to the median for both groups, so this run does not show severe tail instability. The polling-based result-file check adds a small measurement-resolution component; it is the same for both engines after the `pollMs=5` improvement.

## Statistical analysis

The primary model is a two-group linear model:

`latency_ms = intercept + engine_effect + error`

With PowerSync as the reference group, the engine effect is the difference between group means. Because the two groups may have different variances, Welch's two-sample t-test is used for the mean difference. The Mann-Whitney U test is included as a distribution-robust comparison of ranks.

- Mean difference, PowerSync minus ElectricSQL: **56.139 ms**
- Bootstrap 95% CI for mean difference: **[55.488, 56.773] ms**
- Welch t-test: **t = 170.120, p = 3.49084e-209**
- Mann-Whitney U test: **U = 10000.0, p = 2.562e-34**
- Rank-biserial effect size (positive means higher PowerSync latency): **1.000**

Both tests address the narrow question of whether the observed latency distributions differ under this local setup. They do not establish that one technology is universally faster.

## Visual aids

- [Latency distributions](latency-distributions.png)
- [Latency by iteration](latency-by-iteration.png)
- [Summary table](summary.csv)

## Interpretation and limitations

The result supports a lower latency for ElectricSQL in this setup, while PowerSync has a higher central latency. The comparison is observational and local: each engine uses a separate Postgres and service container, and the measurement includes the respective synchronization architecture plus client-side processing. The result-file polling loop and Docker scheduling are also part of the measured environment.

For stronger evidence, repeat the experiment across several independent runs, preserve the same warmup and polling settings, report run-level confidence intervals, and compare medians and p95 values in addition to means.
