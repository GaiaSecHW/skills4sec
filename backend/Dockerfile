FROM python:3.11-slim

WORKDIR /app

# 安装 git (同步服务需要)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# 配置 pip 镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY backend/ .

# 复制报告生成器 (skill 处理仍需要)
COPY skill-report-generator/ /skill-report-generator/

# 复制前端静态文件作为初始数据 (首次启动时会被 PVC 数据覆盖)
COPY docs/ /app/docs/

# 注意: skills/ 不再构建时复制, 运行时由 ICSL 同步服务从 Gitea 拉取到 /data/skills/
# 注意: docs/ 的最终数据由 rebuild_site() 生成到 /data/docs/ (PVC 挂载)

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
