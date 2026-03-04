# Firewall Policy Automation System - Backend

## 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── database.py          # 数据库配置
│   ├── api/                 # API 路由
│   ├── core/                # 核心配置（Celery等）
│   ├── models/              # SQLAlchemy 模型
│   ├── schemas/             # Pydantic 模型
│   ├── tasks/               # Celery 异步任务
│   └── utils/               # 工具函数
├── requirements.txt         # 依赖包
└── README.md
```

## 数据库表设计

### 1. orders（工单表）
- id: 主键
- order_no: 工单编号（唯一）
- title: 工单标题
- description: 工单描述
- excel_file_path: Excel文件路径
- status: 工单状态（pending/processing/completed/failed）
- created_by: 创建人
- created_at: 创建时间
- updated_at: 更新时间

### 2. policies（策略表）
- id: 主键
- order_id: 工单ID（外键）
- firewall_id: 防火墙ID（外键）
- source_zone: 源区域
- dest_zone: 目标区域
- source_ip: 源IP
- dest_ip: 目标IP
- service: 服务/端口
- action: 动作（permit/deny）
- is_merged: 是否已合并
- merged_policy_id: 合并后的策略ID
- push_status: 推送状态
- push_result: 推送结果
- pushed_at: 推送时间
- created_at: 创建时间
- updated_at: 更新时间

### 3. firewalls（防火墙配置表）
- id: 主键
- name: 防火墙名称
- type: 防火墙类型（fortigate/hillstone/leadsec/h3c）
- host: 主机地址
- port: SSH端口
- username: 用户名
- password: 密码（加密存储）
- config: 其他配置（JSON格式）
- is_active: 是否启用
- created_at: 创建时间
- updated_at: 更新时间

### 4. operation_logs（操作日志表）
- id: 主键
- order_id: 工单ID（外键）
- operation_type: 操作类型
- operation_detail: 操作详情
- operator: 操作人
- result: 操作结果（success/failed）
- error_message: 错误信息
- created_at: 操作时间

## 技术栈

- **FastAPI**: Web 框架
- **SQLAlchemy**: ORM
- **PostgreSQL**: 数据库
- **Redis**: 缓存 + Celery broker
- **Celery**: 异步任务队列
- **Paramiko**: SSH 连接
- **Socket.IO**: WebSocket 实时通信
- **Pydantic**: 数据验证

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/firewall_db"
export REDIS_URL="redis://localhost:6379/0"
```

### 3. 初始化数据库
```bash
# 使用 Alembic 进行数据库迁移
alembic init alembic
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

### 4. 启动应用
```bash
# 启动 FastAPI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动 Celery Worker
celery -A app.core.celery_app worker --loglevel=info
```

## API 文档

启动应用后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 开发计划

### Phase 1（Week 1-2）- 基础框架 ✅
- [x] FastAPI 项目初始化
- [x] 数据库表设计
- [x] Redis + Celery 配置
- [ ] 基础 CRUD API

### Phase 2（Week 3-4）- 核心业务
- [ ] Excel 解析模块
- [ ] 防火墙匹配逻辑
- [ ] 策略合并优化算法
- [ ] WebSocket 实时通信

### Phase 3（Week 5-6）- 推送功能
- [ ] SSH 连接管理
- [ ] 策略查询模块（4种防火墙）
- [ ] Celery 异步推送任务
- [ ] 实时进度反馈
