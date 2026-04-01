"""
启动脚本 - 同时运行 HTTP 和 HTTPS 服务器

用法: py -3.11 run.py
"""
import asyncio
import os
import ssl
import sys
from datetime import datetime, timezone

import uvicorn

# 确保从 backend/ 目录导入
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings


def validate_ssl_cert(cert_path: str, key_path: str) -> bool:
    """验证 SSL 证书文件有效性和未过期"""
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        print(f"[SSL] 错误: 证书文件不存在 (cert={cert_path}, key={key_path})")
        return False

    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_path, key_path)

        # 检查证书是否过期
        cert = ctx.get_certificate()
        if cert and hasattr(cert, 'not_valid_after_utc'):
            if cert.not_valid_after_utc < datetime.now(timezone.utc):
                print(f"[SSL] 错误: 证书已过期 (过期时间: {cert.not_valid_after_utc})")
                return False
        return True
    except ssl.SSLError as e:
        print(f"[SSL] 错误: 证书验证失败 - {e}")
        return False
    except Exception as e:
        print(f"[SSL] 错误: 证书加载异常 - {e}")
        return False


async def main():
    """同时启动 HTTP 和 HTTPS 服务器"""
    app = "app.main:app"
    host = "0.0.0.0"

    # HTTP 服务器
    http_config = uvicorn.Config(
        app,
        host=host,
        port=settings.HTTP_PORT,
        log_level="info",
    )
    http_server = uvicorn.Server(http_config)

    servers = [asyncio.create_task(http_server.serve())]

    # HTTPS 服务器（如果启用）
    if settings.SSL_ENABLED:
        cert_path = os.path.join(os.path.dirname(__file__), settings.SSL_CERTFILE)
        key_path = os.path.join(os.path.dirname(__file__), settings.SSL_KEYFILE)

        if validate_ssl_cert(cert_path, key_path):
            https_config = uvicorn.Config(
                app,
                host=host,
                port=settings.HTTPS_PORT,
                ssl_certfile=cert_path,
                ssl_keyfile=key_path,
                log_level="info",
            )
            https_server = uvicorn.Server(https_config)
            servers.append(asyncio.create_task(https_server.serve()))
            print(f"[SSL] HTTPS 服务器启动: https://{host}:{settings.HTTPS_PORT}")
        else:
            print(f"[SSL] 警告: 证书验证未通过，跳过 HTTPS")

    print(f"[HTTP] HTTP 服务器启动: http://{host}:{settings.HTTP_PORT}")

    await asyncio.gather(*servers)


if __name__ == "__main__":
    asyncio.run(main())
