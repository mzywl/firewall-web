# 防火墙项目开发任务

请使用 /plan-task 命令开始规划以下任务：

完成防火墙策略自动化系统的剩余功能开发

项目背景：
- 项目名称：防火墙策略自动化系统
- 代码仓库：https://github.com/mzywl/firewall-web
- 当前分支：dev

技术栈：
- 前端：Vue 3 + TypeScript + Element Plus
- 后端：Python + FastAPI + SQLAlchemy
- 数据库：PostgreSQL 15

待完成功能（按优先级）：

1. 预览页面功能（高优先级，2-3天）
   - 显示策略列表
   - 策略合并预览
   - 推送目标显示

2. 推送功能（高优先级，5-7天）
   - SSH 连接管理（Paramiko）
   - 防火墙类型支持（Fortigate、Hillstone、Leadsec、H3C）
   - 异步任务（Celery）
   - 实时进度（WebSocket）

3. 策略合并算法（中优先级，3-4天）
   - 参考：/home/lishiyu/qhec9-ez5fr/lishiyu/excel/excel.py

4. 历史记录页面（中优先级，2-3天）

5. 防火墙配置管理（中优先级，3-4天）

请创建详细的实施计划。
