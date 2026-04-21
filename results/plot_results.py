import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_bar(df: pd.DataFrame, x_col: str, y_col: str, title: str, ylabel: str, out_file: Path) -> None:
    plt.figure(figsize=(9, 5))
    plt.bar(df[x_col], df[y_col])
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xlabel("策略")
    plt.tight_layout()
    plt.savefig(out_file, dpi=160)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="从 CSV 绘制毕业设计实验指标图。")
    parser.add_argument("--input", required=True, help="CSV 文件路径。")
    parser.add_argument("--outdir", default="results/figures", help="图表输出目录。")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(in_path)

    required = [
        "strategy",
        "p95_ms",
        "qps",
        "cpu_util_percent",
        "memory_util_percent",
        "cost_per_1k_req",
        "scale_events",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"缺少列: {missing}")

    plot_bar(
        df,
        "strategy",
        "p95_ms",
        "P95 延迟对比",
        "延迟（毫秒）",
        out_dir / "p95_latency.png",
    )
    plot_bar(
        df,
        "strategy",
        "qps",
        "吞吐量对比",
        "QPS",
        out_dir / "throughput_qps.png",
    )
    plot_bar(
        df,
        "strategy",
        "cpu_util_percent",
        "CPU 利用率对比",
        "CPU 利用率（%）",
        out_dir / "cpu_utilization.png",
    )
    plot_bar(
        df,
        "strategy",
        "memory_util_percent",
        "内存利用率对比",
        "内存利用率（%）",
        out_dir / "memory_utilization.png",
    )
    plot_bar(
        df,
        "strategy",
        "cost_per_1k_req",
        "每千请求成本对比",
        "成本",
        out_dir / "cost_per_1k_req.png",
    )
    plot_bar(
        df,
        "strategy",
        "scale_events",
        "伸缩事件次数对比",
        "事件次数",
        out_dir / "scale_events.png",
    )

    print(f"图表已输出到: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
