# 毕设实验仓库启动说明

这个仓库提供了一个可直接落地的最小实验基线，包含：
- Kubernetes 微服务部署模板
- HPA（基于 CPU）自动伸缩
- 多指标 HPA 模板（QPS/延迟占位）
- VPA 模板
- Locust 压测脚本
- 论文图表自动作图脚本

## 目录结构

```text
deploy/
  base/
  monitoring/
  hpa/
  vpa/
loadtest/
  locust/
results/
  raw/
  processed/
  figures/
```

## 环境准备

- Kubernetes 集群（Kind、Minikube 或云上托管集群）
- `kubectl`
- `helm`（用于监控栈）
- `python` 3.10+
- `locust`（执行：`pip install -r loadtest/locust/requirements.txt`）

## 快速开始

1. 创建命名空间并部署基础服务：

```bash
kubectl apply -f deploy/base/namespace.yaml
kubectl apply -f deploy/base/deployment.yaml
kubectl apply -f deploy/base/service.yaml
```

2. 安装 metrics-server（CPU HPA 必需）：

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

3. 启用基线 HPA：

```bash
kubectl apply -f deploy/hpa/hpa-cpu.yaml
kubectl get hpa -n thesis-demo -w
```

4. 本地端口转发（用于压测）：

```bash
kubectl -n thesis-demo port-forward svc/sample-api 8080:80
```

5. 运行 Locust 压测：

```bash
locust -f loadtest/locust/locustfile.py --host http://127.0.0.1:8080
```

6. 将实验结果整理为 `results/processed/experiment_metrics.csv`，然后画图：

```bash
python results/plot_results.py --input results/processed/experiment_metrics.csv --outdir results/figures
```

## 监控栈（可选但强烈建议）

安装 Prometheus + Grafana：

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace
```

Prometheus Adapter 配置模板位置：
- `deploy/monitoring/prometheus-adapter-values.yaml`

## 建议实验路线（对应论文）

- 先跑 `hpa-cpu.yaml`，产出基线数据
- 再改造 `hpa-multimetric-template.yaml`，跑多指标实验
- 再接入 `vpa-template.yaml`，做对比实验：
  - 静态配置
  - HPA（CPU）
  - HPA（多指标）
  - HPA + VPA
