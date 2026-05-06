# 毕设实验仓库启动说明（4组对照 + 可复现）

本仓库用于完成“基于容器编排的微服务弹性伸缩策略研究与实践”的实验部分。

## 1. 实验目标

固定 Minikube 环境，完成 4 组策略对照并保证可重复执行：
- `static`: 固定副本，禁用 HPA/VPA。
- `hpa_cpu`: CPU 单指标 HPA。
- `hpa_multi`: CPU + Memory + QPS 自定义指标 HPA。
- `hpa_vpa`: HPA（多指标）+ VPA（Initial）协同。

## 2. 目录结构

```text
deploy/
  base/
  hpa/
  monitoring/
  vpa/
loadtest/
  locust/
results/
  raw/
  processed/
  figures/
scripts/
  experiment.config.json
  run_experiments.ps1
```

## 3. 环境要求

- Windows PowerShell 5+（或 PowerShell 7）
- Minikube（建议 v1.33+）
- kubectl（建议 v1.29+）
- Helm（建议 v3.14+）
- Python 3.10+
- Locust（`pip install -r loadtest/locust/requirements.txt`）
- 结果分析依赖（`pip install -r results/requirements.txt`）

## 4. 从零复现步骤

1. 启动 Minikube 并确认集群可用。
2. 部署基础服务：

```powershell
kubectl apply -f deploy/base/namespace.yaml
kubectl apply -f deploy/base/deployment.yaml
kubectl apply -f deploy/base/service.yaml
```

3. 安装 metrics-server（CPU/Memory HPA 必需）：

```powershell
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

4. 安装监控与自定义指标链路（Prometheus + Adapter）。
   - 使用 `deploy/monitoring/prometheus-adapter-values.yaml` 作为 Adapter rules。
   - 确认 `kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1"` 能查询到 `http_requests_per_second`。

5. 执行全量实验（4组 * 3次）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_experiments.ps1
```

## 5. 实验配置与输出

配置文件：`scripts/experiment.config.json`
- 默认场景：`burst`
- 默认重复次数：`3`
- 默认压测：`users=80`, `spawn_rate=10`, `run_time=5m`

输出目录规则：
`results/raw/{strategy}/{scenario}/{run_id}`

每次 run 产物包含：
- `locust_stats.csv`, `locust_stats_history.csv`, `locust_failures.csv`, `locust_exceptions.csv`
- `top_pods.log`（周期采样）
- `hpa.yaml`, `vpa.yaml`, `hpa_describe.txt`
- `events_before.txt`, `events_after.txt`
- `manifest.json`（环境、参数、版本、commit）

汇总产物：
- `results/processed/experiment_metrics.csv`（每 run 一行）
- `results/processed/experiment_metrics_summary.csv`（均值+标准差）
- `results/figures/*.png`

## 6. 指标口径

性能：`P95/P99`, `QPS`, `failure_rate`
资源：`cpu_util_percent`, `memory_util_percent`
稳定性：`scale_events`, `oscillation_events`
成本代理：`cost_per_1k_req`

说明：成本为代理指标（基于 CPU/Memory 使用量加权估算），用于论文横向对比，不代表云厂商真实账单。

## 7. 数据质量校验

`results/aggregate_experiment.py` 默认执行：
- 缺列检查
- 空值检查
- 异常值区间检查
- 每策略 run 数检查（必须等于配置 `repeats`）

任一校验失败将直接报错并停止出图。

## 8. 单策略冒烟（2分钟）

可在 `scripts/experiment.config.json` 暂时调整：
- `repeats=1`
- `run_time="2m"`
- `strategies` 只保留一组

完成后改回正式参数再跑全量。

## 9. 常见故障排查

- `kubectl top` 无数据：检查 metrics-server Pod 与 APIService 状态。
- 自定义指标不存在：检查 Adapter rules 与 Prometheus 指标名是否一致。
- HPA 不扩容：检查 requests 设置、负载强度、HPA target 值、冷却窗口。
- Locust 连接失败：检查 `port-forward` 是否正常、服务端口是否为 `8080:80`。

## 10. 论文复现声明建议

建议在论文中写明：
- 本实验支持“流程重跑、数据追溯、趋势复现”；
- 不要求跨机器逐点数值完全一致，主要比较策略趋势与统计结果；
- 所有结果由 `manifest.json + raw csv + summary csv + figures` 共同支撑。
