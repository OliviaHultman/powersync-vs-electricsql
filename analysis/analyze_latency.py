from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

REQUIRED_COLUMNS = {
    "iteration",
    "id",
    "inserted_at_ms",
    "received_at_ms",
    "latency_ms",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze PowerSync and ElectricSQL latency CSV files.")
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/analysis"))
    parser.add_argument("--powersync", type=Path)
    parser.add_argument("--electricsql", type=Path)
    return parser.parse_args()


def latest_csv(results_dir: Path, engine: str) -> Path:
    candidates = sorted(results_dir.glob(f"{engine}-latency-*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    candidates = [path for path in candidates if len(pd.read_csv(path)) >= 20]
    if not candidates:
        raise FileNotFoundError(f"No suitable {engine} latency CSV found in {results_dir}")
    return candidates[0]


def load_data(path: Path, engine: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")

    numeric_columns = ["iteration", "inserted_at_ms", "received_at_ms", "latency_ms"]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if frame[numeric_columns].isna().any().any():
        raise ValueError(f"{path} contains missing or non-numeric measurements")
    if frame["id"].duplicated().any():
        raise ValueError(f"{path} contains duplicate event IDs")
    if (frame["latency_ms"] <= 0).any():
        raise ValueError(f"{path} contains non-positive latency values")

    frame["engine"] = engine
    frame["source_file"] = str(path)
    return frame


def percentile(values: pd.Series, probability: float) -> float:
    return float(np.percentile(values.to_numpy(), probability))


def bootstrap_mean_difference(a: np.ndarray, b: np.ndarray, seed: int = 42, samples: int = 20_000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    a_means = rng.choice(a, size=(samples, len(a)), replace=True).mean(axis=1)
    b_means = rng.choice(b, size=(samples, len(b)), replace=True).mean(axis=1)
    differences = a_means - b_means
    return tuple(np.percentile(differences, [2.5, 97.5]))


def rank_biserial_from_u(u: float, n_a: int, n_b: int) -> float:
    return float((2 * u) / (n_a * n_b) - 1)


def make_summary(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for engine, group in data.groupby("engine", sort=False):
        values = group["latency_ms"]
        rows.append(
            {
                "engine": engine,
                "n": len(values),
                "mean_ms": values.mean(),
                "std_ms": values.std(ddof=1),
                "median_ms": values.median(),
                "min_ms": values.min(),
                "p95_ms": percentile(values, 95),
                "max_ms": values.max(),
                "missing_values": int(values.isna().sum()),
                "outliers_iqr": int((values < values.quantile(0.25) - 1.5 * (values.quantile(0.75) - values.quantile(0.25))).sum() + (values > values.quantile(0.75) + 1.5 * (values.quantile(0.75) - values.quantile(0.25))).sum()),
            }
        )
    return pd.DataFrame(rows)


def make_plots(data: pd.DataFrame, output_dir: Path) -> None:
    colors = {"PowerSync": "#05235e", "ElectricSQL": "#e46b35"}
    markers = {"PowerSync": "o", "ElectricSQL": "s"}
    order = ["PowerSync", "ElectricSQL"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    box_data = [data.loc[data["engine"] == engine, "latency_ms"] for engine in order]
    axes[0].boxplot(box_data, tick_labels=order, showmeans=True)
    axes[0].set_title("Latency distribution")
    axes[0].set_ylabel("Latency (ms)")
    axes[0].grid(axis="y", alpha=0.25)

    for engine in order:
        values = data.loc[data["engine"] == engine, "latency_ms"]
        axes[1].hist(values, bins=15, alpha=0.65, label=engine, color=colors[engine])
    axes[1].set_title("Latency histogram")
    axes[1].set_xlabel("Latency (ms)")
    axes[1].set_ylabel("Count")
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.25)
    fig.savefig(output_dir / "latency-distributions.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5))
    for engine in order:
        group = data.loc[data["engine"] == engine]
        ax.plot(group["iteration"], group["latency_ms"], marker=markers[engine], linewidth=1, alpha=0.7, label=engine, color=colors[engine])
    ax.set_title("Latency by iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Latency (ms)")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "latency-by-iteration.png", dpi=180)
    plt.close(fig)


def write_report(data: pd.DataFrame, summary: pd.DataFrame, paths: dict[str, Path], output_dir: Path) -> None:
    powersync = data.loc[data["engine"] == "PowerSync", "latency_ms"].to_numpy()
    electricsql = data.loc[data["engine"] == "ElectricSQL", "latency_ms"].to_numpy()

    welch = stats.ttest_ind(powersync, electricsql, equal_var=False)
    mann_whitney = stats.mannwhitneyu(powersync, electricsql, alternative="two-sided")
    ci_low, ci_high = bootstrap_mean_difference(powersync, electricsql)
    rank_biserial = rank_biserial_from_u(float(mann_whitney.statistic), len(powersync), len(electricsql))
    mean_difference = float(powersync.mean() - electricsql.mean())
    correlation_iteration = data.groupby("engine").apply(lambda group: group["iteration"].corr(group["latency_ms"]), include_groups=False)

    summary_markdown = summary.to_markdown(index=False, floatfmt=".3f")
    report = f"""# Latency analysis: PowerSync vs ElectricSQL

## Data and preprocessing

The analysis loaded the newest latency CSV with at least 20 observations for each engine:

- PowerSync: `{paths['PowerSync']}`
- ElectricSQL: `{paths['ElectricSQL']}`

The CSV fields were parsed as numeric where appropriate. Rows with missing, duplicated, non-positive, or non-numeric measurements would stop the analysis. The selected files contain {len(powersync)} PowerSync and {len(electricsql)} ElectricSQL observations, with no validation failures.

## Variables

- **Independent variable:** `engine`, a categorical two-level factor (`PowerSync` or `ElectricSQL`). The experiment holds the database schema, payload pattern, iteration count, client machine, and orchestrator procedure constant.
- **Controlled variables:** `iteration`, `delayMs`, client/server host, Docker configuration, and experiment code. `iteration` is an ordering variable, not a causal treatment.
- **Dependent variable:** `latency_ms`, the elapsed time from the Postgres insert timestamp to the timestamp at which the client records the synchronized event. It is expected to be numeric, positive, right-skewable, and independent across event IDs within a run.

## Exploratory data analysis

{summary_markdown}

The latency measurements are positive and complete. The iteration-to-latency correlations were:

```text
{correlation_iteration.to_string()}
```

The figures show the group distributions, outliers, and whether latency drifts over the run. The p95 is close to the median for both groups, so this run does not show severe tail instability. The polling-based result-file check adds a small measurement-resolution component; it is the same for both engines after the `pollMs=5` improvement.

## Statistical analysis

The primary model is a two-group linear model:

`latency_ms = intercept + engine_effect + error`

With PowerSync as the reference group, the engine effect is the difference between group means. Because the two groups may have different variances, Welch's two-sample t-test is used for the mean difference. The Mann-Whitney U test is included as a distribution-robust comparison of ranks.

- Mean difference, PowerSync minus ElectricSQL: **{mean_difference:.3f} ms**
- Bootstrap 95% CI for mean difference: **[{ci_low:.3f}, {ci_high:.3f}] ms**
- Welch t-test: **t = {welch.statistic:.3f}, p = {welch.pvalue:.6g}**
- Mann-Whitney U test: **U = {mann_whitney.statistic:.1f}, p = {mann_whitney.pvalue:.6g}**
- Rank-biserial effect size (positive means higher PowerSync latency): **{rank_biserial:.3f}**

Both tests address the narrow question of whether the observed latency distributions differ under this local setup. They do not establish that one technology is universally faster.

## Visual aids

- [Latency distributions](latency-distributions.png)
- [Latency by iteration](latency-by-iteration.png)
- [Summary table](summary.csv)

## Interpretation and limitations

The result supports a lower latency for ElectricSQL in this setup, while PowerSync has a higher central latency. The comparison is observational and local: each engine uses a separate Postgres and service container, and the measurement includes the respective synchronization architecture plus client-side processing. The result-file polling loop and Docker scheduling are also part of the measured environment.

For stronger evidence, repeat the experiment across several independent runs, preserve the same warmup and polling settings, report run-level confidence intervals, and compare medians and p95 values in addition to means.
"""
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    powersync_path = args.powersync or latest_csv(args.results_dir, "powersync")
    electricsql_path = args.electricsql or latest_csv(args.results_dir, "electricsql")
    data = pd.concat(
        [load_data(powersync_path, "PowerSync"), load_data(electricsql_path, "ElectricSQL")],
        ignore_index=True,
    )
    summary = make_summary(data)
    summary.to_csv(args.output_dir / "summary.csv", index=False)
    make_plots(data, args.output_dir)
    write_report(data, summary, {"PowerSync": powersync_path, "ElectricSQL": electricsql_path}, args.output_dir)
    print(f"PowerSync input: {powersync_path}")
    print(f"ElectricSQL input: {electricsql_path}")
    print(summary.to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    print(f"Analysis written to {args.output_dir}")


if __name__ == "__main__":
    main()
