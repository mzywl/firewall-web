# ============================================================
# Stage 1: build（产出 dist/）
# ============================================================
FROM node:20-alpine AS builder

# 显式清空代理（宿主机可能设了 HTTP_PROXY，容器内 127.0.0.1 指向自己会卡）
ENV HTTP_PROXY="" \
    HTTPS_PROXY="" \
    http_proxy="" \
    https_proxy="" \
    ALL_PROXY="" \
    no_proxy="localhost,127.0.0.1"

WORKDIR /app

# 先复制 lockfile 装依赖（缓存友好）
COPY package*.json ./
COPY tsconfig*.json ./
COPY vite.config.ts ./
RUN npm config set registry https://registry.npmmirror.com && \
    npm ci --no-audit --no-fund || npm install --no-audit --no-fund

# 再复制源码
COPY . .

# 编译期环境变量（base 路径，可选）
ARG VITE_BASE=/
ARG VITE_API_BASE_URL=/api
ARG VITE_SOCKET_URL=""
ENV VITE_BASE=$VITE_BASE \
    VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SOCKET_URL=$VITE_SOCKET_URL

# tsc 类型检查 + vite build
RUN npm run build

# ============================================================
# Stage 2: serve（nginx 服务静态 + SPA 兜底）
# ============================================================
FROM nginx:1.27-alpine

# 清空 nginx 默认配置，写入 SPA-friendly 配置
RUN rm -f /etc/nginx/conf.d/default.conf
COPY <<'EOF' /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # SPA 入口：永不缓存（dist 升级时浏览器能立即拿到新 hash）
    location = / {
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
        add_header Pragma "no-cache" always;
        add_header Expires "0" always;
        try_files /index.html =404;
    }
    location = /index.html {
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
        add_header Pragma "no-cache" always;
        add_header Expires "0" always;
    }

    # 静态资源（vite build 出的 assets 带 hash，可长缓存）
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    # SPA: 任何非 /assets/ 的 GET 都尝试找文件，找不到就回 index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

# 复制 build 产物
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# nginx:alpine 默认 CMD 是 nginx -g "daemon off;"，直接继承
