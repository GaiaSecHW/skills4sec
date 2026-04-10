#!/bin/bash
# SkillHub K8s 一键卸载脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="skillhub"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# 检查 kubectl
command -v kubectl &>/dev/null || error "kubectl 未安装"

# 检查 namespace 是否存在
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
    error "Namespace $NAMESPACE 不存在，无需卸载"
fi

echo "========================================="
echo "   SkillHub K8s 一键卸载"
echo "========================================="
echo ""

echo "当前 $NAMESPACE 命名空间下的资源:"
kubectl get all -n "$NAMESPACE"
echo ""

# 确认
read -p "确认删除以上所有资源？(y/N) " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { info "已取消"; exit 0; }

read -p "是否同时删除持久化数据 (PVC)？(y/N) " delete_pvc

# 按逆序删除资源
info "删除 Ingress..."
kubectl delete -f "$SCRIPT_DIR/07-ingress.yaml" --ignore-not-found=true

info "删除 Backend..."
kubectl delete -f "$SCRIPT_DIR/05-backend-deployment.yaml" --ignore-not-found=true

info "删除 Gitea..."
kubectl delete -f "$SCRIPT_DIR/04-gitea-deployment.yaml" --ignore-not-found=true

info "删除 MySQL..."
kubectl delete -f "$SCRIPT_DIR/03-mysql-statefulset.yaml" --ignore-not-found=true

info "删除 Secrets..."
kubectl delete -f "$SCRIPT_DIR/06-secrets.yaml" --ignore-not-found=true

# 删除 PVC
if [[ "$delete_pvc" =~ ^[Yy]$ ]]; then
    info "删除 PVC..."
    kubectl delete pvc --all -n "$NAMESPACE" --ignore-not-found=true
else
    info "保留 PVC，数据未删除"
fi

# 删除 Namespace
info "删除 Namespace $NAMESPACE..."
kubectl delete -f "$SCRIPT_DIR/02-namespace.yaml" --ignore-not-found=true

echo ""
echo "========================================="
echo "   卸载完成！"
echo "========================================="
