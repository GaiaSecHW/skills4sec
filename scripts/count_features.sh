#!/bin/bash
# 功能点统计脚本
# 统计 API 端点 + 前端功能模块

echo "=== 功能点统计 ==="

# 后端 API 端点统计
backend_endpoints=$(grep -c "@router\." backend/app/api/audit.py 2>/dev/null || echo "0")
echo "后端 API 端点: $backend_endpoints"

# 前端功能函数统计 - 统计所有包含 audit/Audit 的 async function
frontend_audit=$(grep -E "async function.*[Aa]udit|function.*[Aa]udit" docs/assets/app.js 2>/dev/null | wc -l || echo "0")
echo "前端审计功能: $frontend_audit"

# 总计
total=$((backend_endpoints + frontend_audit))
echo ""
echo "总功能点数: $total"
