FROM nginx:alpine

# 复制配置
COPY nginx.conf /etc/nginx/nginx.conf

# 复制证书生成脚本
COPY generate-cert.sh /docker-entrypoint.d/40-generate-cert.sh

# 复制前端静态文件
COPY ../docs /usr/share/nginx/html

# 确保 SSL 目录存在并设置权限
RUN mkdir -p /etc/nginx/ssl && chmod +x /docker-entrypoint.d/40-generate-cert.sh
