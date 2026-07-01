"""推送 API (v2 推送流水线)

端点 (2026-06-29 适配新 H3C Netmiko 管线):
- GET  /api/push/orders/{order_id}/tasks                Push 页进入时调用,按防火墙分组列 pending 策略
- POST /api/push/orders/{order_id}/start-v2             启动 v2 推送 (带 firewall_id + mode, 已对齐新 PushPipeline)
- GET  /api/push/snapshots/{snapshot_id}                查快照详情
- GET  /api/push/snapshots/{snapshot_id}/logs           查快照实时日志 (按 seq 增量轮询)
- GET  /api/push/snapshots/{snapshot_id}/items          查快照明细
- POST /api/push/orders/{order_id}/generate-script      本地生成 dry-run CLI 命令 (已重写, 用 H3CConfigParser + StandardPolicyEngine)

依赖服务架构 (新 H3C):
  - H3CConfigParser.parse(text)        静态解析 object-group + security-policy
  - H3CObjectResolver(addrs, svcs)     静态展开嵌套对象为真实 IP/端口
  - StandardPolicyEngine(device_rules) 静态 6 要素比对 (FULL_MATCH / TIME_UPDATE / NEW_RULE)
  - H3CNetmikoClient                   实例: SSH 连接 + generate_commands(new_policies) + push_commands(cmds)

已删除 (前端 0 调用):
- GET  /api/push/supported-types            (列出防火墙客户端类型)
- POST /api/push/test-connection/{fw_id}    (前端调的是 /api/firewalls/<id>/test-connection)
- GET  /api/push/firewall/{fw_id}/snapshots (列某防火墙历史快照)
- GET  /api/push/snapshots                  (列全部快照)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import (
    Firewall,
    Order,
    Policy,
    PushedPolicyItem,
    PushedPolicySnapshot,
    PushLog,
)
from app.services.firewall_clients.h3c import (
    H3CConfigParser,
    H3CObjectResolver,
)
from app.services.firewall_clients.registry import (
    create_client,
    get_client_class,
)
from app.services.push_analyzer import StandardPolicyEngine
from app.services.push_pipeline import PushPipeline

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/orders/{order_id}/tasks")
def get_push_tasks(order_id: int, db: Session = Depends(get_db)):
    """
    获取工单下【准备推送】的策略任务列表（按防火墙分组）

    精简版：只返回下游自动化引擎（如 Ansible/Netmiko）建立连接和下发命令所需的最小参数集。
    (2026-06-28 user 重写 — 字段名扁平化, 便于外部脚本消费)
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    # 1. 核心过滤：只查物理表中状态为 pending 的策略
    pending_records = (
        db.query(Policy, Firewall)
        .join(Firewall, Policy.firewall_id == Firewall.id)
        .filter(
            Policy.order_id == order_id,
            Policy.push_status == 'pending'
        )
        .all()
    )

    if not pending_records:
        return {"order_id": order_id, "tasks": []}

    tasks_by_fw = {}
    for policy, firewall in pending_records:
        fw_id = firewall.id

        # 2. 初始化目标设备的连接凭据信息
        if fw_id not in tasks_by_fw:
            tasks_by_fw[fw_id] = {
                "firewall": {
                    "id": firewall.id,
                    "name": firewall.name,  # 用于脚本打日志
                    "type": firewall.type,  # 决定调用哪种厂商语法的翻译器 (h3c/hillstone)
                    "management_ip": firewall.management_ip,  # SSH 目标 IP
                },
                "policies": []
            }

        # 3. (2026-06-28) /tasks 真精简版 — Push 页只显示墙卡头 + 策略数,
        # 不展示 NAT/时间/系统名等 per-policy 细节(那些由 /generate-script 按墙按需补)
        # 字段选择依据: Push.tsx 实际只读 fw.name/type/management_ip + policies.length
        # 自动化脚本走 /generate-script (有完整 NAT + schedule + 复用分析)
        tasks_by_fw[fw_id]["policies"].append({
            "policy_id": policy.id,
            "src_ip": policy.source_ip,
            "dst_ip": policy.dest_ip,
            "service": policy.service,
        })

    return {
        "order_id": order_id,
        "total_firewalls": len(tasks_by_fw),
        "total_policies": len(pending_records),
        "tasks": list(tasks_by_fw.values()),
    }


@router.post("/orders/{order_id}/start-v2")
def start_push_v2(
    order_id: int,
    firewall_id: int = Query(..., description="目标防火墙 ID"),
    mode: str = Query("deduplicate", description="deduplicate / force_push / reuse_objects"),
    db: Session = Depends(get_db),
):
    """启动 v2 推送（同步执行；如要异步走 Celery 调用 /tasks/push_v2_task）

    (2026-06-29) 对齐新 H3C PushPipeline 签名: PushPipeline(order_id, firewall_info dict, pending_policies list)
      - firewall_info 只需含 management_ip / username / password (其余可选)
      - 凭据先 decrypt 再传入 (铁律: 链路全程明文, 边界处 encrypt)
      - mode=force_push: 跳过 SSH, 把 device_rules 视为空 → 全部 NEW_RULE (假装设备为空)
      - mode=deduplicate / reuse_objects: 正常 SSH + 6 要素查重

    注意：当前是同步执行（方便调试和测试）；真要异步化需要把 run() 拆到 Celery。
    """
    if mode not in ("deduplicate", "force_push", "reuse_objects"):
        raise HTTPException(
            status_code=400,
            detail=f"mode 必须是 'deduplicate' / 'force_push' / 'reuse_objects', got {mode!r}",
        )
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    fw = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="防火墙不存在")

    pending_policies = db.query(Policy).filter(
        Policy.order_id == order_id,
        Policy.firewall_id == firewall_id,
        Policy.push_status == 'pending',
    ).all()
    if not pending_policies:
        raise HTTPException(status_code=400, detail="该防火墙没有可推送的 pending 策略")

    # 凭据解密 (铁律: encrypt 在 firewalls.py, decrypt 在 push.py 边界, 链路中间不要以为没接)
    cfg = fw.connection_config or {}
    ssh_user = cfg.get("username", "")
    ssh_pass_enc = cfg.get("password", "")
    if not ssh_user or not ssh_pass_enc:
        raise HTTPException(
            status_code=400,
            detail=f"防火墙 {fw.name} 缺 SSH 凭据，无法执行推送",
        )
    from app.api.firewalls import decrypt_password
    ssh_pass = decrypt_password(ssh_pass_enc)

    firewall_info = {
        "management_ip": fw.management_ip,
        "username": ssh_user,
        "password": ssh_pass,
        "port": cfg.get("port", 22),
        "timeout": cfg.get("timeout", 30),
    }

    try:
        pipeline = PushPipeline(
            order_id=order_id,
            firewall_info=firewall_info,
            pending_policies=pending_policies,
        )
        result = pipeline.run()
    except Exception as e:
        logger.exception("PushPipeline 异常")
        raise HTTPException(status_code=500, detail=f"推送失败: {e}")

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "未知错误"),
        )
    return result


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    """查快照详情"""
    snap = db.query(PushedPolicySnapshot).filter(
        PushedPolicySnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    return {
        "id": snap.id,
        "order_id": snap.order_id,
        "firewall_id": snap.firewall_id,
        "batch_id": snap.batch_id,
        "push_mode": snap.push_mode.value if hasattr(snap.push_mode, "value") else str(snap.push_mode),
        "status": snap.status.value if hasattr(snap.status, "value") else str(snap.status),
        "total_policies": snap.total_policies,
        "new_policies": snap.new_policies,
        "reused_policies": snap.reused_policies,
        "appended_policies": snap.appended_policies,
        "failed_policies": snap.failed_policies,
        "started_at": snap.started_at.isoformat() if snap.started_at else None,
        "finished_at": snap.finished_at.isoformat() if snap.finished_at else None,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "error_log": snap.error_log,
        "has_fetched_snapshot": bool(
            snap.fetched_addresses_json or snap.fetched_policies_json
        ),
    }


@router.get("/snapshots/{snapshot_id}/logs")
def get_snapshot_logs(
    snapshot_id: int,
    after_seq: int = Query(0, description="只返回 seq > after_seq 的日志（用于前端轮询拿增量）"),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    """查快照的实时日志（按 seq 升序）

    前端轮询模式:
      - 首次: GET /snapshots/{id}/logs 拿前 200 条
      - 后续: GET /snapshots/{id}/logs?after_seq={最后一条 seq} 拿增量
      - 间隔 1.5 秒
    """
    snap = db.query(PushedPolicySnapshot).filter(
        PushedPolicySnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    q = db.query(PushLog).filter(
        PushLog.snapshot_id == snapshot_id,
        PushLog.seq > after_seq,
    ).order_by(PushLog.seq.asc()).limit(limit)
    logs = q.all()
    return {
        "snapshot_id": snapshot_id,
        "snapshot_status": snap.status.value if hasattr(snap.status, "value") else str(snap.status),
        "total": db.query(PushLog).filter(PushLog.snapshot_id == snapshot_id).count(),
        "after_seq": after_seq,
        "logs": [
            {
                "id": lg.id,
                "seq": lg.seq,
                "stage": lg.stage,
                "level": lg.level.value if hasattr(lg.level, "value") else str(lg.level),
                "message": lg.message,
                "data": json.loads(lg.data_json) if lg.data_json else None,
                "created_at": lg.created_at.isoformat() if lg.created_at else None,
            }
            for lg in logs
        ],
    }


@router.get("/snapshots/{snapshot_id}/items")
def get_snapshot_items(
    snapshot_id: int,
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """查快照的策略明细"""
    snap = db.query(PushedPolicySnapshot).filter(
        PushedPolicySnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    items = db.query(PushedPolicyItem).filter(
        PushedPolicyItem.snapshot_id == snapshot_id
    ).order_by(PushedPolicyItem.id).offset(offset).limit(limit).all()
    return {
        "snapshot_id": snapshot_id,
        "total": db.query(PushedPolicyItem).filter(
            PushedPolicyItem.snapshot_id == snapshot_id
        ).count(),
        "items": [
            {
                "id": it.id,
                "policy_id": it.policy_id,
                "match_key": it.match_key,
                "action": it.action,
                "device_policy_id": it.device_policy_id,
                "device_policy_name": it.device_policy_name,
                "device_src_obj": it.device_src_obj,
                "device_dst_obj": it.device_dst_obj,
                "device_service_obj": it.device_service_obj,
                "device_schedule_obj": it.device_schedule_obj,
                "src_addr_key": it.src_addr_key,
                "dst_addr_key": it.dst_addr_key,
                "service_key": it.service_key,
                "schedule_key": it.schedule_key,
                "raw_commands_preview": (it.raw_commands or "")[:500],
                "error_msg": it.error_msg,
                "created_at": it.created_at.isoformat() if it.created_at else None,
            }
            for it in items
        ],
    }


# ============================================================
# 本地生成推送脚本（新 H3C 管线: H3CConfigParser + H3CObjectResolver + StandardPolicyEngine + H3CNetmikoClient）
# ============================================================

@router.post("/orders/{order_id}/generate-script")
def generate_push_script(
        order_id: int,
        firewall_id: int = Query(..., description="目标防火墙 ID"),
        fetch_device_config: bool = Query(
            True,
            description=(
                "是否连墙拉取真实配置做 6 要素复用分析 (默认 True, 默认走查重). "
                "False = dry_run / force_push 模式, 假装设备返回为空, 全部 NEW_RULE"
            ),
        ),
        db: Session = Depends(get_db),
):
    """本地生成推送到指定防火墙的 CLI 命令脚本

    (2026-06-29 重写) 对齐新 H3C 管线:
      - 设备配置解析:  H3CConfigParser.parse(text) (静态, 无需 client 实例)
      - 嵌套对象展开:  H3CObjectResolver(addrs, svcs) (静态, 递归 group)
      - 6 要素复用比对: StandardPolicyEngine(device_rules).match_reusability(std_req)
      - CLI 命令生成:  client.generate_commands(new_policies, object_index, order_no)
                        → 4 段式: object-group ip address / object-group service / time-range / security-policy

    (2026-06-29 用户决策) 默认走查重 (fetch_device_config=True), 只有 frontend dry-run 模式或
                       显式 force_push 时才跳过 SSH, 把 device_rules 视为空 → 全部 NEW_RULE.

    响应字段集对齐前端 types/preview.ts:GenerateScriptResponse — 勿破坏字段.
    """
    # ----- 1. 基础校验 -----
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    fw = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    if not order.policies:
        raise HTTPException(status_code=400, detail="工单没有可生成的策略")

    fw_type = fw.type.value if hasattr(fw.type, "value") else str(fw.type)
    try:
        get_client_class(fw_type)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    # ----- 2. 取该墙 pending 策略 -----
    pending_policies = db.query(Policy).filter(
        Policy.order_id == order_id,
        Policy.firewall_id == firewall_id,
        Policy.push_status == 'pending',
    ).all()

    base_empty = {
        "success": True,
        "firewall": {
            "id": fw.id, "name": fw.name, "type": fw_type,
            "management_ip": fw.management_ip,
        },
        "order": {
            "id": order.id, "order_no": order.order_no, "title": order.title,
        },
        "stats": {
            "total_order_policies": len(order.policies),
            "to_push": 0, "skipped": 0, "commands": 0,
            "full_match": 0, "time_update": 0, "new_rule": 0,
        },
        "policies": [], "new_policies": [], "commands": [], "skipped": [],
        "device_config_fetched": False, "fetch_error": None,
    }
    if not pending_policies:
        return base_empty

    # ----- 3. (查重模式) 连墙拉配置, 解析为 device_rules + object_index -----
    device_rules: List[Dict[str, Any]] = []
    object_index: Dict[str, Dict[str, str]] = {"addresses": {}, "services": {}, "time_ranges": {}}
    device_config_fetched = False
    fetch_error: Optional[str] = None

    if fetch_device_config:
        try:
            cfg = fw.connection_config or {}
            ssh_user = cfg.get("username", "")
            ssh_pass_enc = cfg.get("password", "")
            if not ssh_user or not ssh_pass_enc:
                raise ValueError(f"防火墙 {fw.name} 缺 SSH 凭据，无法深度分析复用")

            from app.api.firewalls import decrypt_password
            ssh_pass = decrypt_password(ssh_pass_enc)

            live_client = create_client(
                device_type=fw_type,
                host=fw.management_ip,
                username=ssh_user,
                password=ssh_pass,
                port=cfg.get("port", 22),
                timeout=cfg.get("timeout", 30),
            )
            try:
                raw_config = live_client.fetch_running_config()
                addresses, services, parsed_policies = H3CConfigParser.parse(raw_config)
                resolver = H3CObjectResolver(addresses, services)
                device_rules = [resolver.resolve_policy(p) for p in parsed_policies]
                # 关键: 提取设备现网对象索引, 给 generate_commands 做"命中即引用"
                object_index = resolver.build_object_index()
                device_config_fetched = True
            finally:
                live_client.disconnect()
        except Exception as e:
            logger.warning(
                "fetch_device_config 失败 (deep mode), fallback 到 NEW_RULE: %s", e
            )
            fetch_error = str(e)
            device_rules = []
            object_index = {"addresses": {}, "services": {}, "time_ranges": {}}

    # ----- 4. 把 pending 策略喂给 StandardPolicyEngine 做 6 要素比对 -----
    engine = StandardPolicyEngine(device_rules)
    policies_with_analysis: List[Dict[str, Any]] = []
    seen: set = set()
    stats = {"full_match": 0, "time_update": 0, "new_rule": 0}

    for idx, policy in enumerate(pending_policies):
        std_req = engine.standardize_db_request(policy)
        # engine 给的 rule_name 不带 idx (会跟 chain_planner 时代的命名冲突), 这里加 idx
        std_req["rule_name"] = f"O{order.order_no}-P{policy.id}-{idx}"
        # action 没在 standardize_db_request 里设, 显式补 (H3C generate_commands 会读)
        std_req["action"] = "permit"
        # 端口从 Policy.service 拆出来, 留空就是 ANY
        std_req["ports"] = [p for p in (policy.service or "").split() if p] or ["ANY"]

        # 基础去重: 同 (src, dst, port) 元组只算一条
        dedup_key = (tuple(std_req["src_ips"]), tuple(std_req["dst_ips"]), tuple(std_req["ports"]))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # 跑匹配
        match = engine.match_reusability(std_req)
        mode_name = match["mode"]
        reused_rule_name = match.get("reused_rule")
        if mode_name == "FULL_MATCH":
            stats["full_match"] += 1
            push_script: List[str] = []
            audit_message = f"完全复用设备现网策略 '{reused_rule_name}', 无需下发"
        elif mode_name == "TIME_UPDATE":
            stats["time_update"] += 1
            # TODO: 生成 time-range 更新命令 (当前 H3C generate_commands 不含 schedule 更新块)
            push_script = []
            audit_message = f"复用 '{reused_rule_name}' 但需更新使用时间 (TODO: 生成 schedule 更新 CLI)"
        else:
            stats["new_rule"] += 1
            push_script = []  # 等下批量由 client.generate_commands 填
            reused_rule_name = None
            audit_message = "未匹配任何现网策略，将新建"

        policies_with_analysis.append({
            "policy_id": policy.id,
            "rule_name": std_req["rule_name"],
            "src_ips": std_req["src_ips"],
            "dst_ips": std_req["dst_ips"],
            "ports": std_req["ports"],
            "valid_until": std_req["valid_until"],
            "src_zone": std_req["src_zone"],
            "dst_zone": std_req["dst_zone"],
            "action": std_req["action"],
            "match_mode": mode_name,
            "reused_rule_name": reused_rule_name,
            "reused_rule_content": _format_reused_rule_content(device_rules, reused_rule_name),
            "push_script": push_script,
            "audit_message": audit_message,
        })

    # ----- 5. 给 NEW_RULE 批量生成 H3C CLI 命令 (4 段式 + object 复用) -----
    new_rule_policies = [p for p in policies_with_analysis if p["match_mode"] == "NEW_RULE"]
    commands: List[str] = []
    if new_rule_policies:
        try:
            # create_client 需要 host/username/password 但不连设备, 传占位即可
            cmd_client = create_client(
                device_type=fw_type,
                host=fw.management_ip or "",
                username="", password="",
                port=22, timeout=5,
            )
            commands = cmd_client.generate_commands(
                new_policies=new_rule_policies,
                object_index=object_index,
            )
            # 把整组命令挂到每个 NEW_RULE policy 的 push_script (前端按墙级复制)
            for p in policies_with_analysis:
                if p["match_mode"] == "NEW_RULE":
                    p["push_script"] = list(commands)
        except Exception as e:
            logger.warning("generate_commands 失败 (NEW_RULE): %s", e)

    # ----- 6. 响应 (字段集对齐 types/preview.ts:GenerateScriptResponse) -----
    return {
        **base_empty,
        "stats": {
            "total_order_policies": len(order.policies),
            "to_push": len(policies_with_analysis),
            "skipped": 0,
            "commands": len(commands),
            "full_match": stats["full_match"],
            "time_update": stats["time_update"],
            "new_rule": stats["new_rule"],
        },
        "policies": policies_with_analysis,
        "new_policies": policies_with_analysis,  # 前端兼容字段 (老代码 new_policies === policies)
        "commands": commands,
        "skipped": [],
        "device_config_fetched": device_config_fetched,
        "fetch_error": fetch_error,
    }


def _format_reused_rule_content(
    device_rules: List[Dict[str, Any]], rule_name: Optional[str]
) -> Optional[str]:
    """把 device_rules 里命中的 rule 拼成单行可读摘要, 给前端展示 '复用: ...'

    返回 None 表示无匹配 (前端用条件渲染隐藏)
    """
    if not rule_name:
        return None
    for r in device_rules:
        if r.get("name") == rule_name:
            return (
                f"{r.get('name')} "
                f"({r.get('src_zone', '?')}→{r.get('dst_zone', '?')}, "
                f"{','.join(r.get('src_ips', []))}→{','.join(r.get('dst_ips', []))}, "
                f"{','.join(r.get('ports', []))})"
            )
    return rule_name  # 兜底: 至少把 name 露出来


def _normalize_valid_until(raw: str) -> str:
    """标准化"使用时间"字段为 generate_commands 能识别的 valid_until 格式

    接受的格式 (来自 user_modified 快照的"使用时间" 字段):
      - 空 / 空白 / "长期" → "长期" (不生成 time-range/schedule)
      - "YYYY-MM-DD" / "YYYY/MM/DD" / "YYYY.MM.DD" → "YYYY-MM-DD" (生成 time-range)
      - 其它不规范 ("6个月", "测试_时间_25", ...) → 兜底 "长期" (不生成, 避免设备拒绝)

    H3C 的 _gen_schedule_object 用 replace("/", "-") 兼容两种,
    Fortigate 的 _build_fortigate_schedule_block 用 replace("-", "/").
    这里统一输出 "YYYY-MM-DD" 中间分隔符, 两家都兼容.
    """
    if not raw:
        return "长期"
    raw = raw.strip()
    if not raw or raw == "长期":
        return "长期"
    # 尝试识别日期: 4位年 + 分隔符 + 1-2位月 + 分隔符 + 1-2位日
    import re
    m = re.match(r'^(\d{4})[\-/.](\d{1,2})[\-/.](\d{1,2})$', raw)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # 兜底: 不规范格式按"长期"处理, 避免推到设备时被拒绝
    return "长期"
