"""回归测试: SKILL.md 坑点 31 死代码清理验证 (Step 5/5)

清理目标 (backend/docs/重构计划-v0.3-C方案.md):
- backend/app/core/policy_merger.py (旧 PolicyMerger, 被 V2 推送替代,
  端口 range 性能炸弹: 1k 端口解析 100+ms, 50 端口已触发 1s+)
- backend/app/api/push.py::POST /api/push/orders/{id}/merge
- frontend/src/lib/api.ts::mergePolicies
本测试保证以上死代码一旦复活就 fail.
"""
import importlib
import os
import re
import subprocess

import pytest

from app.api.push import router as push_router


# ============================================================
# 1. policy_merger.py 文件已删
# ============================================================

def test_policy_merger_file_deleted():
    """PolicyMerger 文件必须删 (端口 range 性能炸弹, 已被 V2 替代)

    兼容性: 检查 host + 容器两路径, 任一存在即 fail.
    期望所有路径都不存在 → 文件没复活 → pass.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(here)
    candidates = [
        os.path.join(backend_dir, "app", "core", "policy_merger.py"),  # host
        "/app/app/core/policy_merger.py",                              # 容器
    ]
    for p in candidates:
        assert not os.path.exists(p), (
            f"{p} 不应存在 (死代码, 端口 range 性能炸弹)"
        )


def test_policy_merger_import_raises():
    """import PolicyMerger 必须 ImportError (防回归)"""
    with pytest.raises(ImportError):
        importlib.import_module("app.core.policy_merger")
    with pytest.raises(ImportError):
        from app.core import policy_merger  # noqa: F401


def test_push_py_does_not_import_policy_merger():
    """push.py 不能 import PolicyMerger (防回退)

    dev 兼容: 容器内 / host 都能找到 push.py
    """
    here = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(here)
    candidates = [
        os.path.join(backend_dir, "app", "api", "push.py"),  # host
        "/app/app/api/push.py",                              # 容器
    ]
    push_path = next((p for p in candidates if os.path.exists(p)), None)
    if push_path is None:
        pytest.skip("push.py 不可访问 (无 backend 挂载)")
    with open(push_path) as f:
        content = f.read()
    assert "from app.core.policy_merger" not in content, (
        "push.py 不应 import policy_merger (死代码)"
    )
    assert "PolicyMerger" not in content, (
        "push.py 不应引用 PolicyMerger (死代码)"
    )


# ============================================================
# 2. /merge 端点已删
# ============================================================

def test_push_router_has_no_merge_endpoint():
    """FastAPI 路由表不应有 /merge 端点"""
    from app.api.push import router as push_router
    routes = [
        (list(r.methods)[0] if r.methods else "?", r.path)
        for r in push_router.routes
    ]
    merge_routes = [(m, p) for m, p in routes if p.endswith("/merge")]
    assert merge_routes == [], f"/merge 端点还存在: {merge_routes}"


def test_merge_endpoint_returns_404():
    """查 OpenAPI 文档: /api/push/orders/{id}/merge 不在 path 里
    (避开 TestClient 跟 httpx 版本不匹配问题)"""
    from app.main import fastapi_app
    schema = fastapi_app.openapi()
    paths = schema.get("paths", {})
    merge_paths = [p for p in paths if p.endswith("/merge")]
    assert merge_paths == [], f"OpenAPI schema 仍含 /merge: {merge_paths}"


# ============================================================
# 3. 前端 mergePolicies 函数已删
# ============================================================

def test_frontend_merge_policies_deleted():
    """前端 api.ts 不应有 mergePolicies 函数"""
    # 容器内 frontend 路径 (构建时复制) 或 host 路径
    candidates = [
        "/app/frontend/src/lib/api.ts",  # 容器内
        "/home/lishiyu/firewall-web/frontend/src/lib/api.ts",  # host
    ]
    api_path = None
    for p in candidates:
        if os.path.exists(p):
            api_path = p
            break
    if api_path is None:
        # 跳过 (frontend 容器没挂, 但部署 dockerfile 会有)
        pytest.skip("frontend/src/lib/api.ts 不可访问 (无 frontend 挂载)")
    with open(api_path) as f:
        content = f.read()
    assert "mergePolicies" not in content, (
        f"{api_path} 不应包含 mergePolicies (死代码, 后端已删)"
    )
    # 同时确认没有引用 /merge URL
    assert "/merge" not in content, (
        f"{api_path} 不应再引用 /merge URL"
    )
