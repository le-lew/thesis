# VPA 使用说明

请先安装 VPA 组件（示例）：

```bash
git clone https://github.com/kubernetes/autoscaler.git
cd autoscaler/vertical-pod-autoscaler
./hack/vpa-up.sh
```

应用模板：

```bash
kubectl apply -f deploy/vpa/vpa-template.yaml
kubectl get vpa -n thesis-demo
```

建议按毕设阶段推进：
- 阶段 1：`updateMode: Off`（只收集推荐值，不自动修改）
- 阶段 2：`updateMode: Initial`（仅在 Pod 创建时应用推荐）
- 阶段 3：`updateMode: Auto`（全自动调整，用于对比稳定性）
