# Kubernetes 部署指南

## 前置条件

- Kubernetes 集群 (1.20+)
- kubectl 已配置
- (可选) Helm 3.x
- (可选) cert-manager 用于 HTTPS

## 文件结构

```
k8s/
├── 02-namespace.yaml           # 命名空间
├── 03-mysql-statefulset.yaml   # MySQL StatefulSet + Service
├── 04-gitea-deployment.yaml    # Gitea Deployment + Service
├── 05-backend-deployment.yaml  # 后端 Deployment + Service
├── 06-secrets.yaml             # Secrets (Token/密钥)
├── 07-ingress.yaml             # Ingress 配置
└── README.md                   # 本文档
```

## 快速部署

### 1. 创建命名空间

```bash
kubectl apply -f 02-namespace.yaml
```

### 2. 创建 Secrets

```bash
# 先修改 06-secrets.yaml 中的值，然后应用
kubectl apply -f 06-secrets.yaml
```

### 3. 部署 MySQL

```bash
kubectl apply -f 03-mysql-statefulset.yaml
```

### 4. 部署 Gitea

```bash
kubectl apply -f 04-gitea-deployment.yaml
```

### 5. 部署后端

```bash
# 先构建并推送镜像
docker build -t your-registry/skillhub-backend:latest ./backend
docker push your-registry/skillhub-backend:latest

# 修改 05-backend-deployment.yaml 中的镜像地址后部署
kubectl apply -f 05-backend-deployment.yaml
```

### 6. 配置 Ingress (可选)

```bash
# 修改 07-ingress.yaml 中的域名后应用
kubectl apply -f 07-ingress.yaml
```

## 一键部署

```bash
kubectl apply -f 02-namespace.yaml
kubectl apply -f 06-secrets.yaml
kubectl apply -f 03-mysql-statefulset.yaml
kubectl apply -f 04-gitea-deployment.yaml
kubectl apply -f 05-backend-deployment.yaml
kubectl apply -f 07-ingress.yaml
```

## 验证部署

```bash
# 查看 Pod 状态
kubectl get pods -n skillhub

# 查看 Service
kubectl get svc -n skillhub

# 查看 Ingress
kubectl get ingress -n skillhub

# 查看日志
kubectl logs -f deployment/skillhub-backend -n skillhub
```

## 常用命令

```bash
# 扩容
kubectl scale deployment skillhub-backend --replicas=3 -n skillhub

# 重启 Pod
kubectl rollout restart deployment/skillhub-backend -n skillhub

# 查看资源使用
kubectl top pods -n skillhub

# 进入容器调试
kubectl exec -it <pod-name> -n skillhub -- sh

# 删除所有资源
kubectl delete namespace skillhub
```

## 生产环境建议

1. **镜像仓库**：使用私有镜像仓库（Harbor/阿里云 ACR）
2. **持久化存储**：MySQL 使用 PVC，静态文件使用 PVC 或对象存储
3. **HTTPS**：配置 cert-manager 自动签发证书
4. **监控**：集成 Prometheus + Grafana
5. **日志**：集成 ELK/Loki
6. **HPA**：配置水平自动扩缩容

```yaml
# HPA 示例
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: skillhub-backend-hpa
  namespace: skillhub
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: skillhub-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```
