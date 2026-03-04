# 防火墙策略自动化系统 - 前端

基于 Vue 3 + TypeScript + Element Plus 的防火墙策略管理系统前端。

## 技术栈

- Vue 3
- TypeScript
- Element Plus
- AG-Grid
- Pinia
- Vue Router
- Axios
- Socket.IO Client

## 项目结构

```
src/
├── views/          # 页面组件
├── components/     # 通用组件
├── api/           # API 调用
├── store/         # Pinia 状态管理
├── router/        # 路由配置
├── assets/        # 静态资源
└── types/         # TypeScript 类型定义
```

## 开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 代码检查
npm run lint
```

## 页面路由

- `/` - 首页
- `/upload` - 文件上传
- `/edit` - 策略编辑
- `/preview` - 策略预览
- `/push` - 策略推送
- `/history` - 历史记录
- `/config` - 防火墙配置
- `/logs` - 操作日志
