"""
app/services/firewall_clients/base.py
NetmikoClient 标准基类与通用数据模型
"""
from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException


# ============================================================
# 统一数据模型 (系统普通话)
# ============================================================

@dataclass
class AddressObject:
    name: str
    type: str  # "ip" / "range" / "subnet" / "group"
    value: str
    members: List[str] = field(default_factory=list)

@dataclass
class ServiceObject:
    name: str
    protocol: str
    dst_port: str
    members: List[str] = field(default_factory=list)

@dataclass
class FirewallPolicy:
    policy_id: str
    name: str
    src_zone: str
    dst_zone: str
    src_addrs: List[str]
    dst_addrs: List[str]
    services: List[str]
    schedule: Optional[str]
    action: str
    enabled: bool

@dataclass
class PushProgress:
    seq: int
    command: str
    output: str
    success: bool
    elapsed_ms: int
    error: str = ""


# ============================================================
# Netmiko 抽象基类
# ============================================================

class NetmikoFirewallClient(abc.ABC):
    """基于 Netmiko 的防火墙客户端标准基类"""

    def __init__(self, host: str, username: str, password: str, port: int = 22, timeout: int = 30):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.device_type = self._get_netmiko_device_type()
        self.connection = None

    @abc.abstractmethod
    def _get_netmiko_device_type(self) -> str:
        """返回 Netmiko 对应的 device_type (例如 'hp_comware', 'cisco_ios')"""
        pass

    def connect(self) -> None:
        if not self.connection:
            try:
                self.connection = ConnectHandler(
                    device_type=self.device_type,
                    host=self.host,
                    username=self.username,
                    password=self.password,
                    port=self.port,
                    timeout=self.timeout,
                    global_delay_factor=2
                )
            except (NetmikoTimeoutException, NetmikoAuthenticationException) as e:
                raise ConnectionError(f"Netmiko 连接失败 {self.host}:{self.port} - {e}")

    def disconnect(self) -> None:
        if self.connection:
            self.connection.disconnect()
            self.connection = None

    def fetch_running_config(self) -> str:
        """拉取配置文本 (Netmiko 自动处理翻页)"""
        self.connect()
        return self.connection.send_command(self._get_show_config_command())

    @abc.abstractmethod
    def _get_show_config_command(self) -> str:
        pass

    @abc.abstractmethod
    def generate_commands(self, new_policies: List[Dict[str, Any]]) -> List[str]:
        """将标准策略字典翻译为对应厂商的 CLI 命令数组"""
        pass

    def push_commands(self, commands: List[str], progress_callback=None) -> List[PushProgress]:
        """批量推送配置并捕获单行错误"""
        self.connect()
        results = []

        # 自动进入配置模式
        self.connection.config_mode()

        for seq, cmd in enumerate(commands, 1):
            t0 = time.time()
            try:
                output = self.connection.send_command(cmd, expect_string=r".*")
                elapsed = int((time.time() - t0) * 1000)
                success, error = self._check_standard_error(output)
                progress = PushProgress(seq=seq, command=cmd, output=output, success=success, elapsed_ms=elapsed, error=error)
            except Exception as e:
                progress = PushProgress(seq=seq, command=cmd, output="", success=False, elapsed_ms=0, error=str(e))

            results.append(progress)
            if progress_callback:
                progress_callback(progress)

            if not progress.success:
                break

        # 退出配置模式并保存
        self.connection.exit_config_mode()
        self._post_push_save()
        return results

    def _check_standard_error(self, output: str) -> Tuple[bool, str]:
        err_kws = ["% Unrecognized", "Error:", "Invalid", "Incomplete", "Wrong parameter"]
        for kw in err_kws:
            if kw.lower() in output.lower():
                return False, f"执行失败，包含错误词 {kw}: {output}"
        return True, ""

    def _post_push_save(self) -> None:
        pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()