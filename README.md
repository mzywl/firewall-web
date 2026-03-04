# Firewall Web

防火墙策略自动化 Web 系统

## 项目结构

```
firewall-web/
├── frontend/          # Vue 3 前端
├── backend/           # FastAPI 后端
├── docker-compose.yml # Docker 编排配置
└── README.md
```

## 技术栈

- **前端**: Vue 3 + TypeScript + Vite
- **后端**: FastAPI + Python 3.11
- **容器化**: Docker + Docker Compose

## 开发流程

1. 所有功能开发在 `dev` 分支进行
2. 提交 PR 到 `dev` 分支进行代码审查
3. 审查通过后合并到 `dev`
4. 定期从 `dev` 合并到 `main` 进行发布

## 分支策略

- `main`: 生产环境分支（受保护）
- `dev`: 开发分支
- `feature/*`: 功能分支
- `hotfix/*`: 紧急修复分支

## 快速开始

（待补充）
