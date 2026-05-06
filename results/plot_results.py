import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def _plot_bar_with_error(df: pd.DataFrame, x: str, y: str, err: str, title: str, ylabel: str, out_file: Path) -> None:
    plt.figure(figsize=(10, 5))
    plt.bar(df[x], df[y], yerr=df[err], capsize=5)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xlabel("Strategy")
    plt.tight_layout()
    plt.savefig(out_file, dpi=180)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot thesis experiment charts with std error bars.")
    parser.add_argument("--input", required=True, help="CSV path (per-run or summary).")
    parser.add_argument("--outdir", default="results/figures", help="Output directory.")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path)

    if "p95_ms_mean" not in df.columns:
        group_cols = ["strategy"]
        if "scenario" in df.columns:
            group_cols.append("scenario")

        df = (
            df.groupby(group_cols, as_index=False)
            .agg(
                p95_ms_mean=("p95_ms", "mean"),
                p95_ms_std=("p95_ms", "std"),
                p99_ms_mean=("p99_ms", "mean"),
                p99_ms_std=("p99_ms", "std"),
                qps_mean=("qps", "mean"),
                qps_std=("qps", "std"),
                failure_rate_mean=("failure_rate", "mean"),
                failure_rate_std=("failure_rate", "std"),
                cpu_util_percent_mean=("cpu_util_percent", "mean"),
                cpu_util_percent_std=("cpu_util_percent", "std"),
                memory_util_percent_mean=("memory_util_percent", "mean"),
                memory_util_percent_std=("memory_util_percent", "std"),
                scale_events_mean=("scale_events", "mean"),
                scale_events_std=("scale_events", "std"),
                oscillation_events_mean=("oscillation_events", "mean"),
                oscillation_events_std=("oscillation_events", "std"),
                cost_per_1k_req_mean=("cost_per_1k_req", "mean"),
                cost_per_1k_req_std=("cost_per_1k_req", "std"),
            )
            .fillna(0.0)
        )

    required = [
        "strategy",
        "p95_ms_mean",
        "p95_ms_std",
        "p99_ms_mean",
        "p99_ms_std",
        "qps_mean",
        "qps_std",
        "failure_rate_mean",
        "failure_rate_std",
        "cpu_util_percent_mean",
        "cpu_util_percent_std",
        "memory_util_percent_mean",
        "memory_util_percent_std",
        "scale_events_mean",
        "scale_events_std",
        "oscillation_events_mean",
        "oscillation_events_std",
        "cost_per_1k_req_mean",
        "cost_per_1k_req_std",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")

    _plot_bar_with_error(df, "strategy", "p95_ms_mean", "p95_ms_std", "P95 Latency", "ms", out_dir / "p95_latency.png")
    _plot_bar_with_error(df, "strategy", "p99_ms_mean", "p99_ms_std", "P99 Latency", "ms", out_dir / "p99_latency.png")
    _plot_bar_with_error(df, "strategy", "qps_mean", "qps_std", "Throughput (QPS)", "QPS", out_dir / "throughput_qps.png")
    _plot_bar_with_error(df, "strategy", "failure_rate_mean", "failure_rate_std", "Failure Rate", "ratio", out_dir / "failure_rate.png")
    _plot_bar_with_error(df, "strategy", "cpu_util_percent_mean", "cpu_util_percent_std", "CPU Utilization", "%", out_dir / "cpu_utilization.png")
    _plot_bar_with_error(df, "strategy", "memory_util_percent_mean", "memory_util_percent_std", "Memory Utilization", "%", out_dir / "memory_utilization.png")
    _plot_bar_with_error(df, "strategy", "scale_events_mean", "scale_events_std", "Scale Events", "count", out_dir / "scale_events.png")
    _plot_bar_with_error(df, "strategy", "oscillation_events_mean", "oscillation_events_std", "Oscillation Events", "count", out_dir / "oscillation_events.png")
    _plot_bar_with_error(df, "strategy", "cost_per_1k_req_mean", "cost_per_1k_req_std", "Cost Proxy per 1k Requests", "cost proxy", out_dir / "cost_per_1k_req.png")

    print(f"charts output: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
