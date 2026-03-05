# Firewall Policy Automation System - Backend API

## Phase 2 更新 - WebSocket 推送功能

### 新增功能

**1. WebSocket 服务端** (`app/core/websocket.py`)
- 集成 Socket.IO 到 FastAPI
- 支持客户端连接/断开
- 房间管理（按工单 ID 分组）
- 实时事件广播：
  - `push_progress` - 推送进度
  - `push_log` - 推送日志
  - `push_status` - 推送状态变更

**2. 策略合并优化算法** (`app/core/policy_merger.py`)
- 相同源IP、目的IP、协议的策略合并
- 端口范围优化（连续端口合并）
- 冗余策略检测

**3. 推送控制 API** (`app/api/push.py`)
- `POST /api/push/orders/{order_id}/start` - 开始推送
- `POST /api/push/orders/{order_id}/merge` - 策略合并分析
- `GET /api/push/orders/{order_id}/status` - 获取推送状态

**4. Celery 异步推送任务** (`app/tasks/push_tasks.py`)
- 异步推送策略到防火墙
- 实时进度更新（通过 WebSocket）
- 推送日志记录和广播
- 错误处理和重试机制

### WebSocket 事件

**客户端 → 服务端：**
```javascript
// 连接
socket.connect()

// 加入工单房间
socket.emit('join_order', { order_id: 1 })

// 离开工单房间
socket.emit('leave_order', { order_id: 1 })
```

**服务端 → 客户端：**
```javascript
// 连接成功
socket.on('connected', (data) => {
  console.log(data.message)
})

// 推送进度
socket.on('push_progress', (data) => {
  // data: { progress: 50, current: 5, total: 10, success: 4, failed: 1 }
})

// 推送日志
socket.on('push_log', (data) => {
  // data: { level: 'info', message: '...', timestamp: 1234567890 }
})

// 推送状态变更
socket.on('push_status', (data) => {
  // data: { status: 'completed', message: '...', success_count: 10, failed_count: 0 }
})
```

### API 文档

#### 1. 开始推送

```http
POST /api/push/orders/{order_id}/start

响应:
{
  "message": "推送任务已启动",
  "task_id": "abc-123",
  "order_id": 1,
  "policies_count": 10
}
```

#### 2. 策略合并分析

```http
POST /api/push/orders/{order_id}/merge

响应:
{
  "message": "策略合并分析完成",
  "original_count": 10,
  "merged_count": 5,
  "redundant_count": 2,
  "redundant_ids": [3, 7],
  "merged_policies": [...]
}
```

#### 3. 获取推送状态

```http
GET /api/push/orders/{order_id}/status

响应:
{
  "order_id": 1,
  "order_status": "processing",
  "total": 10,
  "success": 5,
  "failed": 1,
  "pending": 4,
  "progress": 60
}
```

### 启动应用

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 FastAPI（支持 WebSocket）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动 Celery Worker
celery -A app.core.celery_app worker --loglevel=info

# 启动 Redis（如果未运行）
redis-server
```

### WebSocket 连接

```
ws://localhost:8000/socket.io
```

### 开发计划

### Phase 1（Week 1-2）✅
- [x] FastAPI 项目初始化
- [x] 数据库表设计
- [x] Redis + Celery 配置
- [x] Excel 解析模块
- [x] 防火墙匹配模块
- [x] 核心 CRUD API

### Phase 2（Week 3-4）✅
- [x] WebSocket 服务端
- [x] 策略合并优化算法
- [x] 推送控制 API
- [x] Celery 异步推送任务
- [x] 实时进度和日志广播

### Phase 3（Week 5-6）
- [ ] SSH 连接管理（Paramiko）
- [ ] 4种防火墙策略查询（FortiGate/Hillstone/LeadSec/H3C）
- [ ] 实际推送逻辑实现
- [ ] 推送失败重试机制
- [ ] 推送历史记录查询

### 技术栈

- **FastAPI** - Web 框架
- **Socket.IO** - WebSocket 实时通信
- **Celery** - 异步任务队列
- **Redis** - 缓存 + Celery broker
- **SQLAlchemy** - ORM
- **PostgreSQL** - 数据库
- **Paramiko** - SSH 连接（待实现）

### 前后端联调

前端已完成 WebSocket 客户端集成，现在可以进行联调测试：

1. 启动后端服务（FastAPI + Celery + Redis）
2. 启动前端服务
3. 上传 Excel 文件创建工单
4. 点击"开始推送"按钮
5. 实时查看推送进度和日志

---

**Phase 2 完成！** 🎉
