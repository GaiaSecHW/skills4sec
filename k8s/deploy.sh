#!/bin/bash
# SkillHub K8s 一键部署脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

# 检查密钥文件是否已修改
check_secrets() {
    if grep -q "CHANGE_ME" "$SCRIPT_DIR/06-secrets.yaml"; then
        warn "06-secrets.yaml 中仍有 CHANGE_ME 占位符，请先替换为实际值"
        read -p "是否继续部署？(y/N) " confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || exit 0
    fi
}

wait_for_ready() {
    local label="$1"
    local timeout="${2:-120}"

    info "等待 $label 就绪 (超时 ${timeout}s)..."
    kubectl wait --for=condition=ready pod -l "$label" -n skillhub --timeout="${timeout}s" 2>/dev/null || {
        warn "$label 在 ${timeout}s 内未就绪，继续部署..."
        kubectl get pod -l "$label" -n skillhub
    }
}

echo "========================================="
echo "   SkillHub K8s 一键部署"
echo "========================================="
echo ""

check_secrets

# 1. Namespace
info "创建 Namespace..."
kubectl apply -f "$SCRIPT_DIR/02-namespace.yaml"

# 2. Secrets
info "创建 Secrets..."
kubectl apply -f "$SCRIPT_DIR/06-secrets.yaml"

# 3. MySQL
info "部署 MySQL..."
kubectl apply -f "$SCRIPT_DIR/03-mysql-statefulset.yaml"
wait_for_ready "app=skillhub-mysql" 180

# 创建 Gitea 数据库
info "创建 Gitea 数据库..."
MYSQL_PWD=$(kubectl get secret skillhub-secrets -n skillhub -o jsonpath='{.data.mysql-root-password}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
if [ -n "$MYSQL_PWD" ]; then
    kubectl exec skillhub-mysql-0 -n skillhub -- \
        mysql -uroot -p"$MYSQL_PWD" -e "CREATE DATABASE IF NOT EXISTS gitea CHARACTER SET utf8mb4;" 2>/dev/null && \
        info "Gitea 数据库创建成功" || warn "Gitea 数据库创建失败，可能已存在"
else
    warn "无法获取 MySQL 密码，请手动创建 gitea 数据库"
fi

# 4. Gitea
info "部署 Gitea..."
kubectl apply -f "$SCRIPT_DIR/04-gitea-deployment.yaml"
wait_for_ready "app=skillhub-gitea" 180

# 5. Backend
info "部署 Backend..."
kubectl apply -f "$SCRIPT_DIR/05-backend-deployment.yaml"
wait_for_ready "app=skillhub-backend" 180

# 6. Ingress
info "创建 Ingress..."
kubectl apply -f "$SCRIPT_DIR/07-ingress.yaml"

echo ""
echo "========================================="
echo "   部署完成！"
echo "========================================="
echo ""
kubectl get all -n skillhub
echo ""
echo "Ingress 状态:"
kubectl get ingress -n skillhub
echo ""
info "请确保域名 DNS 已指向集群 Ingress IP"
