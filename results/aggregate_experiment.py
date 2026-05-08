import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd


def _read_top_log(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["pod", "cpu_m", "mem_mib"])

    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or "TOP_FAILED" in line:
            continue
        payload = parts[-1].strip().split()
        if len(payload) < 3:
            continue
        pod = payload[0]
        cpu_raw = payload[1]
        mem_raw = payload[2]
        cpu_m = 0.0
        mem_mib = 0.0

        if cpu_raw.endswith("m"):
            cpu_m = float(cpu_raw[:-1])
        elif cpu_raw:
            cpu_m = float(cpu_raw) * 1000.0

        if mem_raw.lower().endswith("mi"):
            mem_mib = float(mem_raw[:-2])
        elif mem_raw.lower().endswith("gi"):
            mem_mib = float(mem_raw[:-2]) * 1024.0

        rows.append({"pod": pod, "cpu_m": cpu_m, "mem_mib": mem_mib})

    return pd.DataFrame(rows)


def _read_locust_stats(path: Path) -> Dict[str, float]:
    if not path.exists():
        raise FileNotFoundError(f"locust stats missing: {path}")

    df = pd.read_csv(path)
    if "Name" not in df.columns:
        raise ValueError(f"invalid locust stats format: {path}")

    agg = df[df["Name"] == "Aggregated"]
    if agg.empty:
        raise ValueError(f"Aggregated row missing: {path}")

    row = agg.iloc[0]
    required = ["Request Count", "Failure Count", "Average Response Time", "95%", "99%", "Requests/s"]
    missing = [c for c in required if c not in row.index]
    if missing:
        raise ValueError(f"missing columns in locust stats {path}: {missing}")

    req = float(row["Request Count"])
    fail = float(row["Failure Count"])
    return {
        "request_count": req,
        "failure_count": fail,
        "failure_rate": (fail / req) if req > 0 else 0.0,
        "avg_ms": float(row["Average Response Time"]),
        "p95_ms": float(row["95%"]),
        "p99_ms": float(row["99%"]),
        "qps": float(row["Requests/s"]),
    }


def _read_vpa_valid(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "").lower()
    has_vpa = "kind: verticalpodautoscaler" in text or "verticalpodautoscaler" in text
    has_recommendation = "recommendationprovided" in text or "updatemode: initial" in text
    if has_vpa and has_recommendation and "vpa api resource not found" not in text:
        return 1
    return 0


def _count_scale_events(events_path: Path) -> int:
    if not events_path.exists():
        return 0
    text = events_path.read_text(encoding="utf-8", errors="ignore").lower()
    keys = ["scaled up replica set", "scaled down replica set", "successfulrescale"]
    return sum(text.count(k) for k in keys)


def _count_replica_oscillation(events_path: Path) -> int:
    if not events_path.exists():
        return 0
    text = events_path.read_text(encoding="utf-8", errors="ignore").lower()
    up = text.count("scaled up replica set")
    down = text.count("scaled down replica set")
    return int(min(up, down))


def _validate_no_nan(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if df[c].isna().any():
            raise ValueError(f"NaN detected in column: {c}")


def _validate_reasonable(df: pd.DataFrame) -> None:
    checks = {
        "p95_ms": (0, 60000),
        "p99_ms": (0, 60000),
        "qps": (0, 100000),
        "failure_rate": (0, 1),
        "cpu_util_percent": (0, 1000),
        "memory_util_percent": (0, 1000),
    }
    for col, (lo, hi) in checks.items():
        bad = df[(df[col] < lo) | (df[col] > hi)]
        if not bad.empty:
            raise ValueError(f"out-of-range values in {col}: [{lo}, {hi}]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate reproducible experiment outputs.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--raw-root", default="results/raw")
    parser.add_argument("--out", default="results/processed/experiment_metrics.csv")
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    raw_root = Path(args.raw_root)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cpu_req_m = 100.0
    mem_req_mib = 128.0
    cost_cpu_w = float(cfg["cost_proxy"]["cpu_weight"])
    cost_mem_w = float(cfg["cost_proxy"]["memory_weight"])
    cost_scale = float(cfg["cost_proxy"]["scale"])

    records = []

    for strategy in cfg["strategies"]:
      scenario = cfg["experiment"]["scenario"]
      strategy_dir = raw_root / strategy / scenario
      if not strategy_dir.exists():
          continue

      for run_dir in sorted([p for p in strategy_dir.iterdir() if p.is_dir()]):
          stats_path = run_dir / "locust_stats.csv"
          metrics = _read_locust_stats(stats_path)

          top_df = _read_top_log(run_dir / "top_pods.log")
          if not top_df.empty:
              top_df = top_df[top_df["pod"].astype(str).str.startswith("sample-api-")]
          top_samples = int(len(top_df))
          cpu_m = float(top_df["cpu_m"].mean()) if not top_df.empty else cpu_req_m
          mem_mib = float(top_df["mem_mib"].mean()) if not top_df.empty else mem_req_mib

          cpu_util = (cpu_m / cpu_req_m) * 100 if cpu_req_m > 0 else float("nan")
          mem_util = (mem_mib / mem_req_mib) * 100 if mem_req_mib > 0 else float("nan")

          scale_events = _count_scale_events(run_dir / "events_after.txt")
          oscillation = _count_replica_oscillation(run_dir / "events_after.txt")

          cost_proxy = (
              (cpu_m / 1000.0) * cost_cpu_w + (mem_mib / 1024.0) * cost_mem_w
          ) * cost_scale
          cost_per_1k = (cost_proxy / metrics["request_count"] * 1000.0) if metrics["request_count"] > 0 else float("nan")

          records.append(
              {
                  "strategy": strategy,
                  "scenario": scenario,
                  "run_id": run_dir.name,
                  "p95_ms": metrics["p95_ms"],
                  "p99_ms": metrics["p99_ms"],
                  "qps": metrics["qps"],
                  "failure_rate": metrics["failure_rate"],
                  "avg_response_ms": metrics["avg_ms"],
                  "request_count": metrics["request_count"],
                  "failure_count": metrics["failure_count"],
                  "cpu_util_percent": cpu_util,
                  "memory_util_percent": mem_util,
                  "scale_events": scale_events,
                  "oscillation_events": oscillation,
                  "cost_per_1k_req": cost_per_1k,
                  "top_samples": top_samples,
                  "top_sample_fallback": 1 if top_samples == 0 else 0,
                  "vpa_valid": _read_vpa_valid(run_dir / "vpa.yaml"),
              }
          )

    if not records:
        raise RuntimeError("no experiment records found")

    df = pd.DataFrame(records)
    required_cols = [
        "strategy",
        "scenario",
        "run_id",
        "p95_ms",
        "p99_ms",
        "qps",
        "failure_rate",
        "cpu_util_percent",
        "memory_util_percent",
        "cost_per_1k_req",
        "scale_events",
        "oscillation_events",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"missing output columns: {missing}")

    _validate_no_nan(df, [
        "p95_ms",
        "p99_ms",
        "qps",
        "failure_rate",
        "cpu_util_percent",
        "memory_util_percent",
        "cost_per_1k_req",
    ])
    _validate_reasonable(df)

    repeat_expected = int(cfg["experiment"]["repeats"])
    cnt = df.groupby(["strategy", "scenario"]).size().reset_index(name="n")
    bad = cnt[cnt["n"] != repeat_expected]
    if not bad.empty:
        raise ValueError(f"run count mismatch: {bad.to_dict(orient='records')}")

    if int(cfg["experiment"]["repeats"]) > 1:
        top_bad = df[df["top_sample_fallback"] != 0]
        if not top_bad.empty:
            raise ValueError(f"top sampling missing in formal runs: {top_bad[['strategy', 'run_id']].to_dict(orient='records')}")
        if "hpa_vpa" in set(df["strategy"]):
            vpa_bad = df[(df["strategy"] == "hpa_vpa") & (df["vpa_valid"] != 1)]
            if not vpa_bad.empty:
                raise ValueError(f"hpa_vpa runs do not contain real VPA output: {vpa_bad[['run_id']].to_dict(orient='records')}")

    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"wrote per-run metrics: {out_path}")

    summary = (
        df.groupby(["strategy", "scenario"], as_index=False)
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

    summary_path = out_path.parent / "experiment_metrics_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8")
    print(f"wrote summary metrics: {summary_path}")


if __name__ == "__main__":
    main()
