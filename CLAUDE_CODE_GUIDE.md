# 防火墙项目 - Claude Code Agent Team 开发指南

## ✅ 已完成的准备工作

1. ✅ Agent Team Plugin 已安装
2. ✅ 项目配置已完成（.claude/settings.json）
3. ✅ 开发分支已创建：`feature/agent-team-dev-20260306-144018`
4. ✅ 任务文档已创建（.claude/task.md）
5. ✅ 代码已同步到最新

## 🚀 启动开发（需要手动操作）

### 步骤 1：打开新终端并启动 Claude Code

```bash
cd /home/lishiyu/.openclaw/workspace/agents/git-admin/firewall-web
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
claude --plugin-dir ~/.claude/plugins/software-development-team
```

### 步骤 2：在 Claude Code 中执行规划

复制以下命令到 Claude Code：

```
/plan-task 完成防火墙策略自动化系统的剩余功能开发

项目背景：
- 项目名称：防火墙策略自动化系统
- 代码仓库：https://github.com/mzywl/firewall-web
- 当前分支：feature/agent-team-dev-20260306-144018

技术栈：
- 前端：Vue 3 + TypeScript + Element Plus
- 后端：Python + FastAPI + SQLAlchemy
- 数据库：PostgreSQL 15
- 消息队列：Redis + Celery

已完成功能（8项）：
1. Excel 文件上传与解析
2. IP 地址格式化
3. 表格版本追溯（original/formatted/user_modified）
4. 表格编辑功能（双表格设计，全量可编辑）
5. 自动执行推送（勾选后跳过预览）
6. 防火墙匹配（根据目的IP自动匹配）
7. 数据库迁移（4个迁移文件已执行）
8. 基础 API 接口

待完成功能（按优先级）：

高优先级（2项）：
1. 预览页面功能（2-3天）
   - 显示策略列表（表格展示，支持排序筛选）
   - 策略合并预览（显示合并前后数量、规则、详情）
   - 推送目标显示（按防火墙分组、显示连接状态）
   - 操作按钮（返回编辑、开始推送）
   - 涉及文件：frontend/src/views/Preview.vue（新建）、backend/app/api/orders.py

2. 推送功能（5-7天）
   - SSH 连接管理（Paramiko，支持密码/密钥认证，连接池，超时控制）
   - 防火墙类型支持（Fortigate、Hillstone、Leadsec、H3C）
   - 推送流程（连接→配置→执行→保存→退出）
   - 实时进度显示（WebSocket 推送进度）
   - 异步任务（Celery 执行推送任务）
   - 涉及文件：backend/app/services/firewall_push.py、backend/app/tasks/push_tasks.py、backend/app/api/push.py、frontend/src/views/Push.vue

中优先级（3项）：
3. 策略合并算法（3-4天）
   - 端口合并（2183, 2184, 2185 → 2183-2185）
   - IP 合并（10.1.1.1, 10.1.1.2, 10.1.1.3 → 10.1.1.1-10.1.1.3）
   - 策略合并（合并条件：源IP、目的IP、动作相同）
   - 特殊格式保留（CIDR、IP段、端口段）
   - 参考实现：/home/lishiyu/qhec9-ez5fr/lishiyu/excel/excel.py
   - 涉及文件：backend/app/services/policy_merge.py

4. 历史记录页面（2-3天）
   - 工单列表（分页、排序）
   - 筛选功能（按状态、时间、创建人）
   - 工单详情（基本信息、策略列表、推送结果、操作日志）
   - 操作功能（重新推送、导出、删除）
   - 涉及文件：frontend/src/views/History.vue、backend/app/api/orders.py

5. 防火墙配置管理（3-4天）
   - 防火墙列表（显示状态、搜索筛选）
   - 添加/编辑防火墙（名称、类型、主机、端口、凭证）
   - 测试连接（SSH 连接测试）
   - 防火墙分组（按区域、类型、自定义）
   - 涉及文件：frontend/src/views/Firewall.vue、backend/app/api/firewalls.py、backend/app/services/firewall_test.py

关键技术点：
1. SSH 连接：使用 Paramiko 库
2. 防火墙命令生成：支持 4 种防火墙类型（Fortigate、Hillstone、Leadsec、H3C）
3. 异步任务：使用 Celery
4. 实时推送：使用 WebSocket
5. 策略合并：参考 /home/lishiyu/qhec9-ez5fr/lishiyu/excel/excel.py

测试数据：
- 测试文件：/home/lishiyu/桌面/生产-估值系统-基础环境信息表.xlsx
- 测试策略数量：12 条

请创建详细的实施计划，包括：
1. 任务分解（按优先级和依赖关系）
2. 涉及的文件和模块
3. 技术实现方案
4. 风险和注意事项
```

### 步骤 3：编排执行

等待 planner agent 返回计划后，复制计划输出，然后执行：

```
/orchestrate [粘贴上一步的计划输出]
```

### 步骤 4：执行任务

根据 orchestrator 返回的委派计划，按并行组执行任务。

## 📊 预期的并行组

**Group 1: 研究 + 基础实现**
- researcher: 研究 Paramiko、Celery、WebSocket
- software-engineer: 实现预览页面前端
- software-engineer: 实现策略合并算法

**Group 2: 核心功能实现**
- software-engineer: 实现推送功能
- software-engineer: 实现历史记录页面
- software-engineer: 实现防火墙配置管理

**Group 3: 审查和测试**
- code-reviewer: 审查所有新增代码
- qa: 编写单元测试和集成测试
- security: 安全审计

**Group 4: 修复和优化**
- software-engineer: 修复审查中发现的问题

## 🔄 Git 工作流程

开发过程中，Agent 会自动提交代码。你需要定期检查：

```bash
# 查看当前状态
cd /home/lishiyu/.openclaw/workspace/agents/git-admin/firewall-web
git status

# 查看提交历史
git log --oneline -10

# 推送到远程
git push origin feature/agent-team-dev-20260306-144018
```

## 📝 监控日志

Agent 的启动/停止事件会记录到：

```bash
tail -f /tmp/agent-team.log
```

## 🎯 完成标准

所有任务完成后：
1. ✅ 所有功能已实现
2. ✅ 代码已审查
3. ✅ 测试已通过
4. ✅ 代码已提交并推送
5. ✅ 创建 Pull Request 到 dev 分支

## 📖 参考资料

- 项目计划：~/.openclaw/workspace/test-agent-team/firewall-project-plan.md
- 旧系统代码：/home/lishiyu/qhec9-ez5fr/lishiyu/excel/excel.py
- 测试数据：/home/lishiyu/桌面/生产-估值系统-基础环境信息表.xlsx

## ⚠️ 注意事项

1. Claude Code 必须在交互式终端中运行，不能后台运行
2. 每次执行 skill 都需要手动确认权限
3. Agent 生成的代码需要人工审查
4. 定期提交代码，避免丢失进度
5. 遇到问题及时查看日志和错误信息

---

现在你可以打开新终端，按照上面的步骤启动 Claude Code 开始开发了！
