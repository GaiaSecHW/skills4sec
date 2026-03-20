from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db, close_db
from app.api.skills import router as skills_router
from app.api.auth import router as auth_router
from app.api.audit import router as audit_router
from app.api.submissions import router as submissions_router


async def init_super_admin():
    """初始化超级管理员"""
    from app.models.user import User
    from app.utils.security import get_password_hash

    employee_id = settings.SUPER_ADMIN_EMPLOYEE_ID
    api_key = settings.SUPER_ADMIN_API_KEY

    if not employee_id or not api_key:
        return  # 未配置则跳过

    existing = await User.filter(employee_id=employee_id).first()
    if existing:
        # 更新密钥确保与 .env 一致
        existing.api_key_hash = get_password_hash(api_key)
        existing.role = "super_admin"
        existing.status = "active"
        existing.is_superuser = True
        existing.is_active = True
        await existing.save()
        print(f"[Init] 超级管理员已更新: {employee_id}")
    else:
        # 创建超级管理员
        await User.create(
            employee_id=employee_id,
            api_key_hash=get_password_hash(api_key),
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
    yield
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

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(skills_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(submissions_router, prefix="/api")


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
    """健康检查"""
    return {"status": "healthy"}
