#!/bin/sh
# 生成自签名 SSL 证书

if [ ! -f /etc/nginx/ssl/cert.pem ]; then
    echo "Generating self-signed SSL certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/key.pem \
        -out /etc/nginx/ssl/cert.pem \
        -subj "/C=CN/ST=Local/L=Local/O=SkillHub/CN=localhost"
    echo "Self-signed certificate generated successfully"
fi
