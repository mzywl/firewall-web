# firewall-web 部署指南

## 🚀 生产部署（推荐）

```bash
# 一键启动（首次会自动 build 镜像）
docker compose up -d --build

# 看启动日志
docker compose logs -f nginx backend

# 访问
浏览器打开 http://your-server/
```

### 架构

```
浏览器
  │
  ▼ 80/443
┌──────────────────────────┐
│  nginx (主入口)          │
│  - /              SPA    │
│  - /api/          FastAPI │
│  - /socket.io/    WebSocket │
└──────────────────────────┘
   │           │           │
   ▼ 80        ▼ 8000      ▼ 5432/6379
frontend    backend     postgres/redis
(nginx)     (uvicorn)   (内网，不暴露)
```

**关键特性：**
- ✅ **零跨域**：浏览器只看到 1 个域名（80），前端 axios / socket.io 都用相对路径
- ✅ **WebSocket 透传**：socket.io 反代带 `Upgrade` / `Connection` 头，1h 长连接
- ✅ **服务发现**：docker compose 内部 DNS，nginx → backend / frontend 用容器名
- ✅ **健康检查**：5 个 service 都有 healthcheck，nginx 等 backend 起来才起
- ✅ **后端 multi-worker**：uvicorn --workers 2

---

## 🛠️ 开发模式（保留支持）

**方式 A：docker compose dev（推荐，跟生产一致）**

`docker-compose.dev.yml`（待补）—— 把 frontend 容器换成 `npm run dev` + volume 挂载，vite 自带 HMR。

**方式 B：纯 host 上 dev**

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（vite dev server 自带 /api /socket.io proxy → 后端 8000）
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

---

## 🔧 常用运维命令

```bash
# 查看容器状态
docker compose ps

# 重启某个服务
docker compose restart backend

# 跑 alembic 升级（生产首次部署后）
docker compose exec backend alembic upgrade head

# 看后端日志
docker compose logs -f --tail=100 backend

# 进入后端 shell
docker compose exec backend bash

# 跑单元测试
docker compose exec backend pytest tests/ -v

# 完整重建（更新代码后）
docker compose up -d --build
```

---

## 🌐 反代到子路径（如 https://host/firewall/）

需要 2 处改动：

**1. 前端构建时设 `VITE_BASE`：**
```yaml
# docker-compose.yml frontend service
environment:
  - VITE_BASE=/firewall/
```
或者改 Dockerfile 的 `ARG VITE_BASE=/firewall/`

**2. nginx 改 location：**
```nginx
location /firewall/ {
    proxy_pass http://frontend_up/;
}
location /firewall/api/ {
    proxy_pass http://backend/api/;
}
location /firewall/socket.io/ {
    proxy_pass http://backend/socket.io/;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## 🔐 HTTPS（推荐生产加）

最简单：用宿主机 nginx/cloudflare/caddy 在最外层做 TLS 终结。

或者直接给本项目的 nginx 加 cert：

```yaml
# docker-compose.yml nginx service 增加
volumes:
  - ./nginx/ssl:/etc/nginx/ssl:ro
ports:
  - "80:80"
  - "443:443"
```

`nginx.conf` 加 443 server block（参考 certbot 文档）。

---

## 🐛 故障排查

| 现象 | 排查 |
|---|---|
| 浏览器看到 502 Bad Gateway | `docker compose ps` — backend/frontend 没起来？等 healthcheck 通过再访问 |
| 推送慢/卡住 | `proxy_read_timeout 300s` 在 nginx.conf 已设；如果是上传 Excel 卡，看 `client_max_body_size 10m` |
| WebSocket 连不上 | 看 nginx 日志：`docker compose logs nginx`；确认 `/socket.io/` 反代有 `Upgrade` 头 |
| 跨域又出现 | 确认浏览器访问的是 nginx (80)，不是直接访问后端 8000 / 前端 5173 |
| 首次部署 500 | 大概率是 alembic 没跑：`docker compose exec backend alembic upgrade head` |
