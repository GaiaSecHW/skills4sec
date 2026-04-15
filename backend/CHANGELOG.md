# Backend Changelog

All notable changes to the backend will be documented in this file.

## [1.1.0] - 2026-04-15

### Added
- Gitea 同步/清理/推送脚本 (`skills/sync_to_gitea.py`, `skills/pull_push_gitea.py`, `skills/cleanup_gitea.py`)
- `.env.example` 新增 MySQL、Report API、OpenAI 配置模板
- Dockerfile 添加 git 系统依赖和 skill-report-generator 依赖安装
- `requirements.txt` 添加 openai 依赖
- GHCR 自动构建 Docker 镜像 workflow
- Kubernetes 部署配置（MySQL StatefulSet、Gitea、Backend、Ingress、Secrets）
- 技能安装命令改为每个技能独立 Gitea 仓库 URL
- Docker 构建包含前端 docs，构建上下文改为项目根目录
- 工作流白盒化调试面板
- 技能 ZIP 下载功能
- 前端配置文件和「我的提交」页面

### Changed
- K8s 部署配置重构：Gitea URL 改为 http，更新 GITEA_REPO 和 GITEA_SKILLS_BASE_URL
- 技能列表、详情、下载接口改为直接读取 skills.json 和 skills 目录
- 报告 API 敏感配置迁移到环境变量，K8s Secrets 统一管理
- Gitea Actions 迁移到后端 APScheduler
- API Key 改为明文存储
- 管理后台 UI 简化
- K8s README 部署文档更新

### Fixed
- clone_repo 在 _find_skill_dir 修正路径后保存 step_details，修复报告生成找不到 skills
- Docker 镜像包含 skills/ 和 skill-report-generator/ 目录
- 添加根目录 .dockerignore，排除 venv 等无关文件
- backend 健康检查路径修正为 /health
- GHCR 镜像名转小写，修复 repository name must be lowercase 错误
- aiomysql 依赖问题
- 我的收藏页面无法正常显示
- httpx 代理配置问题

### Removed
- 清理无用 GitHub Actions workflows，仅保留 build-docker-images
- 移除误提交的 db.sqlite3

## [1.0.0] - 2026-04-09

### Added
- FastAPI 后端框架搭建，Python 3.11 + Tortoise-ORM
- 技能提交 API，集成 Gitea 仓库管理
- 用户认证系统：工号登录、API Key、Refresh Token、角色权限
- 登录日志与管理员操作审计（LoginLog、AdminLog 模型）
- 超级管理员自动初始化
- Repository 数据访问模式，BaseRepository 基类
- 管理后台：提交跟踪、新建提交、前端通知系统
- 统计 API 与工作流优化
- 三步工作流（WorkflowService）
- Docker 部署配置（Dockerfile、docker-compose）
- 结构化日志系统（HarnessLoggingMiddleware）
- 敏感数据脱敏处理器

### Fixed
- 修复 MySQL URL 中密码特殊字符的 URL 编码问题
- 修复非 Windows 系统稀疏克隆时 env 参数类型错误
- 修复管理后台分页、CSV 导出及前端 SPA 挂载
- 修复 Python 3.14 兼容性问题
- 代码检视修复：安全漏洞、代码质量与架构一致性

### Changed
- CORS 配置改为允许所有来源
- 技能列表、详情、下载接口改为直接读取 skills.json 和 skills 目录
- 简化 submissions API 和管理后台 UI
- 删除遗留的 issue_handler.py
