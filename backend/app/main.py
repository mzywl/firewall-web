from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import orders, push
from app.core.websocket import mount_socketio

app = FastAPI(
    title="Firewall Policy Automation API",
    description="防火墙策略自动化管理系统",
    version="0.2.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需要配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 WebSocket
mount_socketio(app)

# 注册路由
app.include_router(orders.router)
app.include_router(push.router)


@app.get("/")
async def root():
    return {"message": "Firewall Policy Automation API", "version": "0.2.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
