from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from app.api import orders, push, firewalls, preview, zone_access, firewall_zones
from app.core.websocket import mount_socketio, sio

# ============================================================
# FastAPI app
# ============================================================
fastapi_app = FastAPI(
    title="Firewall Policy Automation API",
    description="防火墙策略自动化管理系统",
    version="0.2.0"
)

# CORS 配置
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需要配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
fastapi_app.include_router(orders.router)
fastapi_app.include_router(push.router)
fastapi_app.include_router(firewalls.router)
fastapi_app.include_router(preview.router)
fastapi_app.include_router(zone_access.router)
fastapi_app.include_router(firewall_zones.router)


@fastapi_app.get("/")
async def root():
    return {"message": "Firewall Policy Automation API", "version": "0.2.0"}


@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy"}


# ============================================================
# 用 socketio.ASGIApp 包整个 FastAPI app
# 解决 app.mount('/socket.io') 在 FastAPI 0.104+ 上 router 拦截 /socket.io 的 bug
# socketio 接管根 ASGI，把 /socket.io/* 路由给自己，其它转给 fastapi_app
# ============================================================
app = socketio.ASGIApp(sio, fastapi_app)

# 兼容老代码（如果别处 import mount_socketio）
mount_socketio = lambda _: sio  # noqa: E731


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
