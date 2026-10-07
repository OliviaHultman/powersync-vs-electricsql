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
    parser.add_argument("--powersync", type=Path, nargs="+")
    parser.add_argument("--electricsql", type=Path, nargs="+")
    parser.add_argument("--runs", type=int, default=1, help="Number of newest sweeps to pool per engine")
    return parser.parse_args()


def latest_csvs(results_dir: Path, engine: str, runs: int) -> list[Path]:
    candidates = sorted(results_dir.glob(f"{engine}-latency-*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    candidates = [path for path in candidates if len(pd.read_csv(path)) >= 20]
    if not candidates:
        raise FileNotFoundError(f"No suitable {engine} latency CSV found in {results_dir}")
    return candidates[:runs]


def load_data(path: Path, engine: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    if "network_latency_ms" not in frame:
        frame["network_latency_ms"] = 0

    numeric_columns = [
        "iteration",
        "inserted_at_ms",
        "received_at_ms",
        "latency_ms",
        "network_latency_ms",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if frame[numeric_columns].isna().any().any():
        raise ValueError(f"{path} contains missing or non-numeric measurements")
    if (frame["network_latency_ms"] < 0).any():
        raise ValueError(f"{path} contains negative network latency settings")
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
    for (engine, network_latency_ms), group in data.groupby(
        ["engine", "network_latency_ms"], sort=False
    ):
        values = group["latency_ms"]
        rows.append(
            {
                "engine": engine,
                "network_latency_ms": network_latency_ms,
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


def make_plots(data: pd.DataFrame, network_data: pd.DataFrame, output_dir: Path) -> None:
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
        for index, (_, run) in enumerate(group.groupby("source_file", sort=False)):
            ax.plot(run["iteration"], run["latency_ms"], marker=markers[engine], linewidth=1, alpha=0.7, label=engine if index == 0 else None, color=colors[engine])
    ax.set_title("Latency by iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Latency (ms)")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "latency-by-iteration.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    for engine in order:
        engine_data = network_data.loc[network_data["engine"] == engine]
        grouped = engine_data.groupby("network_latency_ms")["latency_ms"]
        medians = grouped.median()
        q1 = grouped.quantile(0.25)
        q3 = grouped.quantile(0.75)
        slope = stats.linregress(engine_data["network_latency_ms"], engine_data["latency_ms"]).slope
        ax.plot(
            medians.index,
            medians.values,
            marker=markers[engine],
            linewidth=1.5,
            label=f"{engine} median (slope {slope:.2f} ms/ms)",
            color=colors[engine],
        )
        ax.fill_between(
            medians.index,
            q1.values,
            q3.values,
            alpha=0.25,
            color=colors[engine],
            label=f"{engine} IQR",
        )
    ax.set_title("Synchronization latency by simulated network latency")
    ax.set_xlabel("Added downstream network latency (ms)")
    ax.set_ylabel("Synchronization latency (ms)")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "latency-by-network-latency.png", dpi=180)
    plt.close(fig)


def write_report(data: pd.DataFrame, summary: pd.DataFrame, paths: dict[str, Path], output_dir: Path) -> None:
    baseline_latency = float(data["network_latency_ms"].min())
    baseline = data.loc[data["network_latency_ms"] == baseline_latency]
    powersync = baseline.loc[baseline["engine"] == "PowerSync", "latency_ms"].to_numpy()
    electricsql = baseline.loc[baseline["engine"] == "ElectricSQL", "latency_ms"].to_numpy()

    if len(powersync) < 2 or len(electricsql) < 2:
        raise ValueError(
            f"At least two baseline observations per engine are required at {baseline_latency:g}ms"
        )
    welch = stats.ttest_ind(powersync, electricsql, equal_var=False)
    mann_whitney = stats.mannwhitneyu(powersync, electricsql, alternative="two-sided")
    ci_low, ci_high = bootstrap_mean_difference(powersync, electricsql)
    rank_biserial = rank_biserial_from_u(float(mann_whitney.statistic), len(powersync), len(electricsql))
    mean_difference = float(powersync.mean() - electricsql.mean())
    correlation_iteration = baseline.groupby("engine").apply(
        lambda group: group["iteration"].corr(group["latency_ms"]),
        include_groups=False,
    )
    network_trends = []
    slopes = {}
    for engine, group in data.groupby("engine", sort=False):
        if group["network_latency_ms"].nunique() < 2:
            network_trends.append(f"- **{engine}:** at least two network latency levels are required.")
            continue
        trend = stats.linregress(group["network_latency_ms"], group["latency_ms"])
        t_critical = stats.t.ppf(0.975, len(group) - 2)
        slopes[engine] = trend
        network_trends.append(
            f"- **{engine}:** {trend.slope:.3f} ms additional synchronization latency per "
            f"1 ms imposed downstream delay, 95% CI [{trend.slope - t_critical * trend.stderr:.3f}, "
            f"{trend.slope + t_critical * trend.stderr:.3f}] (R² = {trend.rvalue**2:.3f})."
        )
    if len(slopes) == 2:
        slope_difference = slopes["ElectricSQL"].slope - slopes["PowerSync"].slope
        difference_se = np.sqrt(slopes["ElectricSQL"].stderr**2 + slopes["PowerSync"].stderr**2)
        z = slope_difference / difference_se
        p_difference = 2 * stats.norm.sf(abs(z))
        network_trends.append(
            f"- **Slope difference (ElectricSQL minus PowerSync):** {slope_difference:.3f} ms/ms, "
            f"95% CI [{slope_difference - 1.96 * difference_se:.3f}, {slope_difference + 1.96 * difference_se:.3f}], "
            f"z = {z:.2f}, p = {p_difference:.3g}."
        )
    network_trend_report = "\n".join(network_trends)

    summary_markdown = summary.to_markdown(index=False, floatfmt=".3f")
    report = f"""# Latency analysis: PowerSync vs ElectricSQL

## Data and preprocessing

The analysis loaded the newest latency CSV file(s) with at least 20 observations for each engine and pooled them when several runs were selected:

- PowerSync: {paths['PowerSync']}
- ElectricSQL: {paths['ElectricSQL']}

The CSV fields were parsed as numeric where appropriate. Rows with missing, duplicated, non-positive, or non-numeric measurements would stop the analysis. The selected files contain {len(powersync)} PowerSync and {len(electricsql)} ElectricSQL baseline observations, with no validation failures.

## Variables

- **Independent variables:** `engine` (`PowerSync` or `ElectricSQL`) and `network_latency_ms`, the fixed one-way delay added to server-to-client traffic by Toxiproxy.
- **Controlled variables:** database schema, payload pattern, client/server host, Docker configuration, warmup, polling interval, and experiment procedure.
- **Dependent variable:** `latency_ms`, the elapsed time from the Postgres insert timestamp to the timestamp at which the client records the synchronized event. It is expected to be numeric, positive, right-skewable, and independent across event IDs within a run.

## Results by engine and network latency

{summary_markdown}

Each row summarizes one engine and one network latency level. The baseline engine comparison below uses the lowest configured network latency ({baseline_latency:.0f} ms). The iteration-to-latency correlations at baseline were:

```text
{correlation_iteration.to_string()}
```

The per-level plot shows mean synchronization latency with standard-error bars. The result-file polling interval adds measurement resolution equally across treatment levels when `pollMs` is held constant.

## Research question 1: engine comparison at baseline

The primary comparison is at the lowest configured network delay:

`latency_ms = intercept + engine_effect + error`

With PowerSync as the reference group, the engine effect is the difference between group means. Because the two groups may have different variances, Welch's two-sample t-test is used for the mean difference. The Mann-Whitney U test is included as a distribution-robust comparison of ranks.

- Mean difference, PowerSync minus ElectricSQL: **{mean_difference:.3f} ms**
- Bootstrap 95% CI for mean difference: **[{ci_low:.3f}, {ci_high:.3f}] ms**
- Welch t-test: **t = {welch.statistic:.3f}, p = {welch.pvalue:.6g}**
- Mann-Whitney U test: **U = {mann_whitney.statistic:.1f}, p = {mann_whitney.pvalue:.6g}**
- Rank-biserial effect size (positive means higher PowerSync latency): **{rank_biserial:.3f}**

Both tests address the narrow question of whether the observed latency distributions differ under this local setup. They do not establish that one technology is universally faster.

## Research question 2: effect of increased network latency

A separate linear trend is estimated for each engine across all configured delay levels:

{network_trend_report}

A positive slope means synchronization latency increased as the imposed server-to-client delay increased. This fixed downstream delay models the path on which synchronized changes reach the client; it is not a general model of Internet conditions.

## Visual aids

- [Baseline latency distributions](latency-distributions.png)
- [Baseline latency by iteration](latency-by-iteration.png)
- [Latency by simulated network latency](latency-by-network-latency.png)
- [Summary table](summary.csv)

## Interpretation and limitations

The comparison is local: each engine uses a separate Postgres and service container, and measurements include synchronization architecture, client processing, polling resolution, and Docker scheduling.

For stronger evidence, repeat each sweep, preserve the same delay levels, warmup, and polling settings, and compare run-level effects in addition to per-event measurements.
"""
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    powersync_paths = args.powersync or latest_csvs(args.results_dir, "powersync", args.runs)
    electricsql_paths = args.electricsql or latest_csvs(args.results_dir, "electricsql", args.runs)
    data = pd.concat(
        [load_data(path, "PowerSync") for path in powersync_paths]
        + [load_data(path, "ElectricSQL") for path in electricsql_paths],
        ignore_index=True,
    )
    levels_by_engine = {
        engine: set(group["network_latency_ms"])
        for engine, group in data.groupby("engine", sort=False)
    }
    if levels_by_engine["PowerSync"] != levels_by_engine["ElectricSQL"]:
        raise ValueError(
            "PowerSync and ElectricSQL CSVs must contain the same network latency levels"
        )
    baseline_latency = float(data["network_latency_ms"].min())
    baseline = data.loc[data["network_latency_ms"] == baseline_latency]
    summary = make_summary(data)
    summary.to_csv(args.output_dir / "summary.csv", index=False)
    make_plots(baseline, data, args.output_dir)
    write_report(data, summary, {
            "PowerSync": ", ".join(f"`{path}`" for path in powersync_paths),
            "ElectricSQL": ", ".join(f"`{path}`" for path in electricsql_paths),
        }, args.output_dir)
    print(f"PowerSync inputs: {', '.join(map(str, powersync_paths))}")
    print(f"ElectricSQL inputs: {', '.join(map(str, electricsql_paths))}")
    print(summary.to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    print(f"Analysis written to {args.output_dir}")


if __name__ == "__main__":
    main()
