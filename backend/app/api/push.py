"""推送 API (v2 推送流水线)

端点 (2026-06-28):
- GET  /api/push/{order_id}/tasks                       Push 页进入时调用,按防火墙分组列 pending 策略 (用户新写)
- POST /api/push/orders/{order_id}/start-v2            启动 v2 推送 (带 firewall_id + mode)
- GET  /api/push/snapshots/{snapshot_id}                查快照详情
- GET  /api/push/snapshots/{snapshot_id}/logs           查快照实时日志 (按 seq 增量轮询)
- GET  /api/push/snapshots/{snapshot_id}/items          查快照明细
- POST /api/push/orders/{order_id}/generate-script      本地生成 dry-run CLI 命令

已删除 (前端 0 调用):
- GET  /api/push/supported-types            (列出防火墙客户端类型)
- POST /api/push/test-connection/{fw_id}    (前端调的是 /api/firewalls/<id>/test-connection)
- GET  /api/push/firewall/{fw_id}/snapshots (列某防火墙历史快照)
- GET  /api/push/snapshots                  (列全部快照)
"""

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database import get_db
from app.services.push_analyzer import (
    PrePushAnalyzer,
    h3c_policies_to_fw_cache,
)
from app.models import (
    Firewall,
    Order,
    Policy,
    PushedPolicyItem,
    PushedPolicySnapshot,
    PushLog,
)
from app.services.firewall_clients.registry import (
    create_client,
    get_client_class,
)
from app.services.push_pipeline import PushPipeline, PushPipelineError

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
    if not order.policies:
        raise HTTPException(status_code=400, detail="工单没有可推送的策略")

    try:
        pipeline = PushPipeline(order_id=order_id, firewall_id=firewall_id, mode=mode, db=db)
        result = pipeline.run()
    except PushPipelineError as e:
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
# 本地生成推送脚本（不连设备、不复用现有对象、不写快照）
# ============================================================

@router.post("/orders/{order_id}/generate-script")
def generate_push_script(
        order_id: int,
        firewall_id: int = Query(..., description="目标防火墙 ID"),
        fetch_device_config: bool = Query(
            False,
            description="是否连墙拉取真实配置做 6 要素复用分析 (False=纯本地 dry-run, 所有策略都 NEW_RULE)",
        ),
        db: Session = Depends(get_db),
):
    """本地生成推送到指定防火墙的 CLI 命令脚本 (结合 2026-06-27 链式寻路+NAT 精准版)"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    fw = db.query(Firewall).filter(Firewall.id == firewall_id).first()
    if not fw:
        raise HTTPException(status_code=404, detail="防火墙不存在")
    if not order.policies:
        raise HTTPException(status_code=400, detail="工单没有可生成的策略")

    # 1. 校验设备类型有 client 实现
    fw_type = fw.type.value if hasattr(fw.type, "value") else str(fw.type)
    try:
        get_client_class(fw_type)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    # 创建基础 client（暂不连设备）
    client = create_client(
        device_type=fw_type, host=fw.management_ip or "", username="", password="", port=22, timeout=5
    )

    # (2026-06-28) usage_time 不再需要单独从 user_modified 加载 — Policy.usage_time 物理表里已有
    # 之前的 usage_time_by_id 是为 chain_planner 服务的, 现在不调 chain_planner 了.

    # ============================================================
    # (2026-06-28) 不走 chain_planner, 直接查 DB 拿 pending 策略
    # 原因: chain_planner 会为跨墙 NAT 透传生成 PASS_THROUGH entry (Policy.id 来自上游墙),
    #       而我们要的是"主防火墙是当前 firewall_id"的直接策略 — 二者不对齐.
    # 简化: SNAT 转换关系已反映在 Policy.source_ip/dest_ip/source_snat_ip 里 (commit 时写入),
    #       这里只需按 firewall_id + push_status='pending' 直查.
    # ============================================================
    pending_policies = db.query(Policy).filter(
        Policy.order_id == order_id,
        Policy.firewall_id == firewall_id,
        Policy.push_status == 'pending',
    ).all()

    if not pending_policies:
        return {
            "success": True,
            "firewall": {
                "id": fw.id, "name": fw.name, "type": fw_type,
                "management_ip": fw.management_ip,
            },
            "order": {"id": order.id, "order_no": order.order_no, "title": order.title},
            "stats": {
                "total_order_policies": len(order.policies),
                "to_push": 0, "skipped": 0, "commands": 0,
                "full_match": 0, "time_update": 0, "new_rule": 0,
            },
            "policies": [], "new_policies": [], "commands": [], "skipped": [],
            "device_config_fetched": False, "fetch_error": None,
        }

    # 直接从 Policy 表构造 raw_policies
    raw_policies: List[Dict[str, Any]] = []
    seen: set = set()
    skipped: List[Dict[str, Any]] = []

    for idx, policy in enumerate(pending_policies):
        # Policy.source_ip / dest_ip 是 '\n' 分隔的多行 IP
        src_ips = [s.strip() for s in (policy.source_ip or "").split('\n') if s.strip()]
        dst_ips = [d.strip() for d in (policy.dest_ip or "").split('\n') if d.strip()]
        # Policy.service 是空格分隔的端口
        ports = [p for p in (policy.service or "").split() if p]

        # 基础去重 (按 src/dst/port 元组)
        dedup_key = (tuple(src_ips), tuple(dst_ips), tuple(ports))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        raw_policies.append({
            "policy_id": policy.id,
            "rule_name": f"O{order.order_no}-P{policy.id}-{idx}",
            "src_ips": src_ips,
            "dst_ips": dst_ips,
            "ports": ports,
            "valid_until": _normalize_valid_until(policy.usage_time),
            "src_zone": policy.device_source_zone or "any",
            "dst_zone": policy.device_dest_zone or "any",
            "action": "permit",
            "original_source_ip": policy.source_ip,  # 保留溯源
            "source_snat_ip": policy.source_snat_ip,  # 用于 SNAT 命令生成
        })

    # 3. 接 PrePushAnalyzer 做设备 6 要素校验（若 fetch_device_config=True）
    analyzer: PrePushAnalyzer
    device_config_fetched = False
    fetch_error = None

    if fetch_device_config:
        try:
            cfg = fw.connection_config or {}
            ssh_user = cfg.get("username", "")
            ssh_pass_enc = cfg.get("password", "")
            if ssh_pass_enc:
                from app.api.firewalls import decrypt_password
                ssh_pass = decrypt_password(ssh_pass_enc)
            else:
                ssh_pass = ""
            if not ssh_user or not ssh_pass:
                raise ValueError(f"防火墙 {fw.id} ({fw.name}) 缺 SSH 凭据，无法深度分析复用")

            client = create_client(
                device_type=fw_type,
                host=fw.management_ip,
                username=ssh_user,
                password=ssh_pass,
                port=cfg.get("port", 22),
                timeout=cfg.get("timeout", 30),
            )
            config_text = client.fetch_running_config()
            addresses, services, policies = client.parse_config(config_text)
            fw_cache = h3c_policies_to_fw_cache(addresses, services, policies)
            analyzer = PrePushAnalyzer(fw_cache)
            device_config_fetched = True
        except Exception as e:
            logger.warning("PrePushAnalyzer: fetch_device_config 失败 (%s), fallback 到 NEW_RULE", e)
            analyzer = PrePushAnalyzer({})
            fetch_error = str(e)
    else:
        analyzer = PrePushAnalyzer({})

    # 4. 跑 6 要素对比，累积命令快照
    commands: List[str] = []
    policies_with_analysis: List[Dict[str, Any]] = []
    stats_full_match = 0
    stats_time_update = 0
    stats_new_rule = 0

    for raw in raw_policies:
        # 喂给 6 要素分析器的是寻路洗白后的物理区与真实 NAT 地址
        analysis = analyzer.analyze_single_policy({
            "device_source_zone": raw["src_zone"],
            "device_dest_zone": raw["dst_zone"],
            "source_ip": raw["src_ips"][0] if raw["src_ips"] else "",
            "dest_ip": raw["dst_ips"][0] if raw["dst_ips"] else "",
            "service": " ".join(raw["ports"]) if raw["ports"] else "",
            "usage_time": raw["valid_until"] if raw["valid_until"] != "长期" else "",
            "original_policy_id": raw["policy_id"],
            "rule_name": raw["rule_name"],
        })

        if analysis["match_mode"] == "FULL_MATCH":
            stats_full_match += 1
        else:
            commands.extend(analysis["push_script"])
            if analysis["match_mode"] == "TIME_UPDATE":
                stats_time_update += 1
            else:
                stats_new_rule += 1

        policies_with_analysis.append({
            **raw,
            "match_mode": analysis["match_mode"],
            "reused_rule_name": analysis["reused_rule_name"],
            "reused_rule_content": analysis["reused_rule_content"],
            "push_script": analysis["push_script"],
            "audit_message": analysis["audit_message"],
        })

    # 5. 对于完全 NEW_RULE 的策略，调用客户端的底层命令行生成器
    if stats_new_rule > 0:
        try:
            new_rule_policies = [p for p in policies_with_analysis if p["match_mode"] == "NEW_RULE"]
            extra_cmds = client.generate_commands(
                new_policies=[
                    {
                        "policy_id": p["policy_id"],
                        "rule_name": p["rule_name"],
                        "src_ips": p["src_ips"],
                        "dst_ips": p["dst_ips"],
                        "ports": p["ports"],
                        "valid_until": p["valid_until"],
                        "src_zone": p["src_zone"],
                        "dst_zone": p["dst_zone"],
                        "action": p["action"],
                    }
                    for p in new_rule_policies
                ],
                existing_addresses=[],
                existing_services=[],
                existing_schedules=[],
            )
            commands.extend(extra_cmds)
        except Exception as e:
            logger.warning("generate_commands 失败 (NEW_RULE): %s", e)

    return {
        "success": True,
        "firewall": {
            "id": fw.id,
            "name": fw.name,
            "type": fw_type,
            "management_ip": fw.management_ip,
        },
        "order": {
            "id": order.id,
            "order_no": order.order_no,
            "title": order.title,
        },
        "stats": {
            "total_order_policies": len(order.policies),
            "to_push": len(policies_with_analysis),
            "skipped": len(skipped),
            "commands": len(commands),
            "full_match": stats_full_match,
            "time_update": stats_time_update,
            "new_rule": stats_new_rule,
        },
        "policies": policies_with_analysis,
        "new_policies": policies_with_analysis,  # 保持前端组件兼容
        "commands": commands,
        "skipped": skipped,
        "device_config_fetched": device_config_fetched,
        "fetch_error": fetch_error,
    }

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
