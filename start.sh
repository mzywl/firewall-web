#!/bin/bash

echo "🚀 启动防火墙策略自动化系统..."

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 错误：未安装 Docker"
    exit 1
fi

# 停止旧容器
echo "📦 停止旧容器..."
docker compose down 2>/dev/null || true

# 构建并启动服务
echo "🔨 构建并启动服务..."
docker compose up -d --build

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo "✅ 检查服务状态..."
docker compose ps

# 运行数据库迁移
echo "🗄️  运行数据库迁移..."
docker compose exec -T backend alembic upgrade head

echo ""
echo "✅ 服务启动完成！"
echo ""
echo "📍 访问地址："
echo "   前端: http://localhost:5173"
echo "   后端 API: http://localhost:8000"
echo "   API 文档: http://localhost:8000/docs"
echo ""
echo "📋 查看日志："
echo "   docker compose logs -f backend"
echo "   docker compose logs -f frontend"
echo "   docker compose logs -f celery"
echo ""
echo "🛑 停止服务："
echo "   docker compose down"
