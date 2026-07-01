"""
app/services/push_pipeline.py
V2 推送主调度器
"""
from __future__ import annotations
import logging
import time

from app.services.firewall_clients.h3c import H3CNetmikoClient, H3CConfigParser, H3CObjectResolver
from app.services.push_analyzer import StandardPolicyEngine

logger = logging.getLogger(__name__)

class PushPipeline:

    def __init__(
        self,
        order_id: int,
        firewall_info: dict,
        pending_policies: list,
        mode: str = "deduplicate",
    ):
        """
        order_id         工单 ID (日志/审计用)
        firewall_info    {management_ip, username, password, port?, timeout?}
        pending_policies List[Policy] 待推送策略
        mode             deduplicate (默认, 走 SSH 拉现网 + 6 要素查重)
                         force_push (跳过 SSH, 把 device_rules 视为空, 全部 NEW_RULE)
                         reuse_objects (TODO: 同 deduplicate, 后续引入 object 级复用增强)
        """
        self.order_id = order_id
        self.fw_info = firewall_info
        self.policies = pending_policies
        self.mode = mode

    def run(self) -> dict:
        client = None
        device_rules: list = []
        try:
            if self.mode == "force_push":
                # 假装设备返回为空 → StandardPolicyEngine([]) 会让所有策略都判 NEW_RULE
                logger.info(">>> [mode=force_push] 跳过 SSH, device_rules = []")
            else:
                logger.info(">>> [Step 1] 连接设备，拉取文本...")
                client = H3CNetmikoClient(
                    host=self.fw_info["management_ip"],
                    username=self.fw_info["username"],
                    password=self.fw_info["password"],
                )
                raw_config = client.fetch_running_config()

                logger.info(">>> [Step 2] 解析文本为内存对象...")
                addrs, svcs, policies = H3CConfigParser.parse(raw_config)

                logger.info(">>> [Step 3] 递归转换真实要素...")
                resolver = H3CObjectResolver(addrs, svcs)
                device_rules = [resolver.resolve_policy(p) for p in policies]

            logger.info(">>> [Step 4] 启动大脑比对复用...")
            engine = StandardPolicyEngine(device_rules)
            new_rules_to_push = []
            stats = {"full_match": 0, "time_update": 0, "new_rule": 0}

            for raw_policy in self.policies:
                std_req = engine.standardize_db_request(raw_policy)
                match_result = engine.match_reusability(std_req)

                if match_result["mode"] == "FULL_MATCH":
                    stats["full_match"] += 1
                elif match_result["mode"] == "TIME_UPDATE":
                    stats["time_update"] += 1
                    # 这里可补充时间更新命令生成逻辑
                else:
                    stats["new_rule"] += 1
                    new_rules_to_push.append(std_req)

            logger.info(">>> [Step 5] 生成 CLI 并下发...")
            all_commands = []
            if new_rules_to_push:
                if client is None:
                    # force_push 模式没有真实 client, 重新建一个占位实例
                    client = H3CNetmikoClient(
                        host=self.fw_info.get("management_ip", ""),
                        username="", password="",
                    )
                all_commands = client.generate_commands(new_rules_to_push)
                push_results = client.push_commands(all_commands)

                failed = [r for r in push_results if not r.success]
                if failed:
                    return {"success": False, "error": f"部分命令失败: {failed[0].error}"}

            return {
                "success": True,
                "stats": stats,
                "pushed_commands_count": len(all_commands),
                "mode": self.mode,
            }

        except Exception as e:
            logger.error(f"流水线异常: {e}")
            return {"success": False, "error": str(e)}

        finally:
            if client and client.connection:
                client.disconnect()