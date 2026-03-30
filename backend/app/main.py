from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.config import settings
from app.core.database import init_db, close_db, check_database_health
from app.core.harness_logging import setup_harness_logging, HarnessLoggingMiddleware, setup_aggregator, stop_aggregator
from app.core.exceptions import register_exception_handlers
from app.api.skills import router as skills_router
from app.api.auth import router as auth_router
from app.api.audit import router as audit_router
from app.api.submissions import router as submissions_router
from app.api.admin import router as admin_router
from app.api.stats import router as stats_router

# 初始化日志
setup_harness_logging(level="DEBUG" if settings.DEBUG else "INFO", log_dir="logs", service_name="SecAgentHub", enable_aggregation=True,)


async def init_super_admin():
    """初始化超级管理员"""
    from app.models.user import User
    from app.utils.security import get_password_hash

    employee_id = settings.SUPER_ADMIN_EMPLOYEE_ID
    api_key = settings.SUPER_ADMIN_API_KEY

    if not employee_id or not api_key:
        return  # 未配置则跳过

    existing = await User.get_or_none(employee_id=employee_id)
    if existing:
        # 更新密钥确保与 .env 一致（明文存储）
        existing.api_key = api_key
        existing.role = "super_admin"
        existing.status = "active"
        existing.is_superuser = True
        existing.is_active = True
        await existing.save(update_fields=["api_key", "role", "status", "is_superuser", "is_active"])
        print(f"[Init] 超级管理员已更新: {employee_id}")
    else:
        # 创建超级管理员（明文存储 API Key）
        await User.create(
            employee_id=employee_id,
            api_key=api_key,
            name=settings.SUPER_ADMIN_NAME or "系统管理员",
            role="super_admin",
            status="active",
            is_superuser=True,
            is_active=True,
        )
        print(f"[Init] 超级管理员已创建: {employee_id}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    await init_db()
    # 初始化超级管理员
    await init_super_admin()
    # 启动日志聚合器
    from app.core.harness_logging.config import LogConfig
    if LogConfig.AGGREGATION_ENABLED:
        await setup_aggregator(LogConfig)
    # 启动定时任务调度器
    from app.tasks.scheduler import setup_scheduler, start_scheduler
    setup_scheduler()
    start_scheduler()
    yield
    # 关闭时停止调度器
    from app.tasks.scheduler import shutdown_scheduler
    shutdown_scheduler()
    # 关闭时停止日志聚合器
    await stop_aggregator()
    # 关闭时清理数据库连接
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="SecAgentHub - AI 技能市场后端 API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 注册异常处理器
register_exception_handlers(app)

# 添加请求日志中间件
app.add_middleware(
        HarnessLoggingMiddleware,
        exclude_paths={"/health", "/metrics", "/", "/favicon.ico"},
    )

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:8000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(skills_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(submissions_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(stats_router, prefix="/api")


@app.get("/")
async def root():
    """API 根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    """健康检查（含数据库连接状态）"""
    db_health = await check_database_health()
    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "database": db_health,
        "version": settings.APP_VERSION,
    }


# 挂载静态文件（管理后台前端）
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/admin")
async def admin_page():
    """管理后台入口"""
    from fastapi.responses import FileResponse
    admin_html = os.path.join(static_dir, "admin", "index.html")
    if os.path.exists(admin_html):
        return FileResponse(admin_html)
    return {"error": "Admin page not found"}
