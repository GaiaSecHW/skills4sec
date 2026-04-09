# Backend Changelog

All notable changes to the backend will be documented in this file.

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
