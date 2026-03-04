# Firewall Policy Automation System - Backend API

## 更新内容

### Phase 1 Week 2 - 核心 API 实现 ✅

**新增功能：**

1. **Excel 解析模块** (`app/core/excel_parser.py`)
   - 支持 .xlsx/.xls 文件解析
   - 自动读取表头和数据
   - 标准化 IP 地址和端口格式
   - 日期格式化处理

2. **防火墙匹配模块** (`app/core/firewall_matcher.py`)
   - 根据 IP 地址自动匹配防火墙设备
   - 支持 CIDR 格式（192.168.1.0/24）
   - 批量 IP 匹配

3. **核心 API 接口** (`app/api/orders.py`)
   - `POST /api/orders/upload` - 上传 Excel 文件并创建工单
   - `GET /api/orders/{order_id}` - 获取工单详情
   - `GET /api/orders/{order_id}/policies` - 获取工单的所有策略
   - `PUT /api/orders/{order_id}/policies` - 批量更新策略

4. **数据库迁移配置** (Alembic)
   - 配置 Alembic 环境
   - 支持数据库版本管理

**技术实现：**
- 文件上传使用 UUID 生成唯一文件名
- Excel 解析使用 openpyxl
- 自动匹配防火墙设备
- 支持批量策略更新

## API 文档

### 1. 上传 Excel 文件

```http
POST /api/orders/upload
Content-Type: multipart/form-data

参数:
- file: Excel 文件 (.xlsx/.xls)
- title: 工单标题（可选）
- created_by: 创建人（可选）

响应:
{
  "id": 1,
  "order_no": "ORD-20260305000000",
  "title": "防火墙策略工单",
  "status": "pending",
  "excel_file_path": "uploads/xxx.xlsx",
  "created_at": "2026-03-05T00:00:00",
  "updated_at": "2026-03-05T00:00:00"
}
```

### 2. 获取工单详情

```http
GET /api/orders/{order_id}

响应:
{
  "id": 1,
  "order_no": "ORD-20260305000000",
  "title": "防火墙策略工单",
  "description": "上传文件: test.xlsx, 共 10 行数据",
  "status": "pending",
  "created_at": "2026-03-05T00:00:00"
}
```

### 3. 获取工单策略列表

```http
GET /api/orders/{order_id}/policies

响应:
[
  {
    "id": 1,
    "order_id": 1,
    "source_zone": "trust",
    "dest_zone": "untrust",
    "source_ip": "192.168.1.0/24",
    "dest_ip": "10.0.0.1",
    "service": "tcp/80",
    "action": "permit",
    "firewall_id": 1,
    "is_merged": 0,
    "push_status": null,
    "created_at": "2026-03-05T00:00:00"
  }
]
```

### 4. 批量更新策略

```http
PUT /api/orders/{order_id}/policies
Content-Type: application/json

请求体:
[
  {
    "id": 1,
    "source_ip": "192.168.2.0/24",
    "dest_ip": "10.0.0.2"
  }
]

响应:
{
  "message": "策略更新成功",
  "updated_count": 1
}
```

## 数据库迁移

```bash
# 初始化迁移（首次）
alembic revision --autogenerate -m "Initial migration"

# 执行迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

## 启动应用

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置数据库连接

# 执行数据库迁移
alembic upgrade head

# 启动 FastAPI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 API 文档：http://localhost:8000/docs

## 开发计划

### Phase 1（Week 1-2）- 基础框架 ✅
- [x] FastAPI 项目初始化
- [x] 数据库表设计
- [x] Redis + Celery 配置
- [x] Excel 解析模块
- [x] 防火墙匹配模块
- [x] 核心 CRUD API

### Phase 2（Week 3-4）- 核心业务
- [ ] 策略合并优化算法
- [ ] WebSocket 实时通信
- [ ] 工单状态管理

### Phase 3（Week 5-6）- 推送功能
- [ ] SSH 连接管理
- [ ] 策略查询模块（4种防火墙）
- [ ] Celery 异步推送任务
- [ ] 实时进度反馈
