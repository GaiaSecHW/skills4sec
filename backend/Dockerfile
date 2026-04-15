FROM python:3.11-slim

WORKDIR /app

# 配置 pip 镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装系统依赖（git 用于克隆仓库）
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# 安装后端依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装报告生成器依赖
COPY skill-report-generator/requirements.txt /tmp/report-requirements.txt
RUN pip install --no-cache-dir -r /tmp/report-requirements.txt && \
    rm -f /tmp/report-requirements.txt

# 复制应用代码
COPY backend/ .

# 复制前端静态文件（docs -> app 上两级目录对应 docs/）
COPY docs/ /docs/

# 复制技能文件和报告生成器
COPY skills/ /skills/
COPY skill-report-generator/ /skill-report-generator/

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
