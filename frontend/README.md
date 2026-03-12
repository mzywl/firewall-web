# 防火墙策略管理系统 - 前端 V2

现代化的防火墙策略自动化管理系统前端界面。

## 技术栈

- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **样式**: Tailwind CSS
- **状态管理**: Zustand
- **数据管理**: TanStack Query
- **路由**: React Router v6
- **实时通信**: Socket.IO Client
- **HTTP 客户端**: Axios
- **图标**: Lucide React

## 功能特性

### ✅ 已实现

1. **文件上传**
   - 拖拽上传 Excel 文件
   - 文件类型验证
   - 上传进度显示

2. **策略编辑**
   - 可编辑表格
   - 版本切换（格式化版本 / 用户编辑版本）
   - 实时保存

3. **策略预览**
   - 版本对比视图
   - 并排显示不同版本
   - 版本历史记录

4. **策略推送**
   - 实时推送进度
   - WebSocket 实时日志
   - 推送状态统计
   - 成功率计算

5. **主题系统**
   - 深色 / 浅色 / 系统主题
   - 主题切换动画
   - 持久化保存

## 项目结构

```
src/
├── components/
│   ├── ui/              # 基础 UI 组件
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Input.tsx
│   │   ├── Badge.tsx
│   │   └── Progress.tsx
│   ├── layout/          # 布局组件
│   │   ├── Header.tsx
│   │   └── Layout.tsx
│   ├── upload/          # 上传相关
│   │   └── FileUploader.tsx
│   ├── table/           # 表格相关
│   │   └── PolicyTable.tsx
│   └── push/            # 推送相关
│       ├── PushProgressBar.tsx
│       └── PushLogViewer.tsx
├── pages/               # 页面组件
│   ├── Home.tsx
│   ├── Upload.tsx
│   ├── Edit.tsx
│   ├── Preview.tsx
│   └── Push.tsx
├── hooks/               # 自定义 Hooks
│   ├── useApi.ts
│   └── useWebSocket.ts
├── lib/                 # 工具库
│   ├── api.ts
│   └── socket.ts
├── types/               # TypeScript 类型
│   └── index.ts
├── stores/              # 状态管理
│   └── theme.ts
├── App.tsx
├── main.tsx
└── index.css
```

## 开发指南

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:5173/

### 构建生产版本

```bash
npm run build
```

### 预览生产构建

```bash
npm run preview
```

## 环境变量

创建 `.env` 文件：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_SOCKET_URL=http://localhost:8000
```

## API 接口

### 工单管理

- `POST /api/orders/upload` - 上传 Excel 文件
- `GET /api/orders/:id` - 获取工单详情
- `GET /api/orders/:id/policies` - 获取策略列表
- `GET /api/orders/:id/versions` - 获取版本列表
- `PUT /api/orders/:id/policies` - 更新策略

### 推送管理

- `POST /api/push/orders/:id/start` - 开始推送
- `POST /api/push/orders/:id/merge` - 策略合并分析
- `GET /api/push/orders/:id/status` - 获取推送状态

### WebSocket 事件

- `push_progress` - 推送进度更新
- `push_log` - 推送日志
- `push_status` - 推送状态变化

## 页面路由

- `/` - 首页
- `/upload` - 文件上传
- `/order/:id/edit` - 策略编辑
- `/order/:id/preview` - 策略预览
- `/order/:id/push` - 策略推送

## 设计特点

### 现代化 UI

- 使用 Tailwind CSS 实现现代化设计
- 流畅的动画和过渡效果
- 响应式布局，支持桌面和平板

### 主题系统

- 支持深色 / 浅色 / 系统主题
- 基于 CSS 变量实现
- 主题切换平滑过渡

### 实时通信

- WebSocket 实时推送进度
- 自动重连机制
- 日志自动滚动

### 用户体验

- 拖拽上传文件
- 表格内联编辑
- 版本对比视图
- 实时状态反馈

## 与后端集成

确保后端服务运行在 `http://localhost:8000`，并且：

1. 启动 FastAPI 服务
2. 启动 Redis
3. 启动 Celery Worker
4. 启动 Socket.IO 服务

## 浏览器支持

- Chrome (推荐)
- Firefox
- Safari
- Edge

## 开发团队

- 前端架构：Claude (AI)
- 代码生成：Gemini (AI)
- 项目管理：纳米

## 许可证

MIT
