FROM nginx:alpine

# 安装 openssl 用于生成自签名证书
RUN apk add --no-cache openssl

# 复制配置
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# 复制证书生成脚本
COPY nginx/generate-cert.sh /docker-entrypoint.d/40-generate-cert.sh

# 复制前端静态文件
COPY docs /usr/share/nginx/html

# 确保 SSL 目录存在并设置权限
RUN mkdir -p /etc/nginx/ssl && chmod +x /docker-entrypoint.d/40-generate-cert.sh
