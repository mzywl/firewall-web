"""防火墙客户端抽象基类

所有厂家的客户端必须实现 parse_config / generate_commands。
SSH 通用部分（连接、按行推送、错误检测）由基类提供。
"""
from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import paramiko


# ============================================================
# 数据类
# ============================================================

@dataclass
class AddressObject:
    """防火墙上的一个地址对象"""
    name: str                 # 设备上的对象名（如 "trust-10.1.1.0"）
    type: str                 # "ip" / "range" / "subnet" / "fqdn" / "group"
    value: str                # "10.1.1.0/24" / "10.1.1.1-10.1.1.10" / "10.1.1.1"
    members: List[str] = field(default_factory=list)  # group 类型的成员名


@dataclass
class ServiceObject:
    """防火墙上的一个服务/端口对象"""
    name: str                 # "TCP-80" / "UDP-53"
    protocol: str             # "tcp" / "udp" / "icmp"
    dst_port: str             # "80" / "80-90" / "1-65535"
    members: List[str] = field(default_factory=list)  # group 类型的成员名


@dataclass
class ScheduleObject:
    """防火墙上的一个时间对象"""
    name: str                 # "截止2025-12-31" / "always"
    schedule_type: str        # "onetime" / "recurring" / "always"
    end_date: Optional[str] = None  # "2025-12-31"


@dataclass
class FirewallPolicy:
    """防火墙上的一个策略"""
    policy_id: str            # 设备上的 ID
    name: str
    src_zone: str
    dst_zone: str
    src_addrs: List[str]      # 源地址对象名列表
    dst_addrs: List[str]      # 目的地址对象名列表
    services: List[str]       # 服务对象名列表
    schedule: Optional[str]   # 时间对象名
    action: str               # "accept" / "deny"
    enabled: bool


@dataclass
class ConnectionTestResult:
    """test_connection 的结果"""
    success: bool
    banner: str = ""
    version: str = ""
    device_type_detected: str = ""
    error: str = ""
    elapsed_ms: int = 0


@dataclass
class PushProgress:
    """推送进度（一条命令一条事件）"""
    seq: int
    command: str
    output: str
    success: bool
    elapsed_ms: int
    error: str = ""


# ============================================================
# 基类
# ============================================================

class FirewallClient(abc.ABC):
    """防火墙客户端抽象基类

    子类必须实现:
        - parse_config(config_text) -> (addresses_df, services_df, policies_df)
        - generate_commands(items)  -> List[str]
        - test_banner()             -> str  (测试连接时拿 banner)

    子类可以覆盖:
        - encode(s)                 -> bytes (默认 utf-8，H3C 是 gb2312)
        - decode(b)                 -> str
        - push_commands()           -> 默认实现：按行 invoke_shell
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        timeout: int = 30,
        device_type: str = "",
        **kwargs: Any,
    ):
        self.host = host
        self.port = port or 22
        self.username = username
        self.password = password
        self.timeout = timeout
        self.device_type = device_type
        self.kwargs = kwargs

        self.ssh: Optional[paramiko.SSHClient] = None
        self.shell = None
        self._connected = False

    # ---------- 编码（子类可覆盖） ----------

    def encode(self, s: str) -> bytes:
        """字符串 → 字节（H3C 用 gb2312，其他默认 utf-8）"""
        return s.encode(self.encoding)

    def decode(self, b: bytes) -> str:
        """字节 → 字符串"""
        return b.decode(self.encoding, errors="ignore")

    @property
    def encoding(self) -> str:
        return "utf-8"

    # ---------- 连接管理 ----------

    def connect(self) -> bool:
        """建立 SSH + invoke_shell"""
        if self._connected:
            return True
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False,
            )
            # 大 width 防命令被截断（H3C display 多）
            self.shell = self.ssh.invoke_shell(width=1000, height=5000)
            self.shell.settimeout(self.timeout)
            # 等初始 banner
            time.sleep(0.5)
            try:
                self.shell.recv(65535)
            except Exception:
                pass
            self._connected = True
            return True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"SSH 连接失败 {self.host}:{self.port} - {e}")

    def disconnect(self) -> None:
        if self.shell:
            try:
                self.shell.close()
            except Exception:
                pass
        if self.ssh:
            try:
                self.ssh.close()
            except Exception:
                pass
        self._connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    # ---------- 测试连接（公开 API） ----------

    def test_connection(self) -> ConnectionTestResult:
        """测试 SSH 连通性 + 拉版本号"""
        t0 = time.time()
        try:
            self.connect()
            try:
                banner = self._read_banner()
                version = self._read_version()
                return ConnectionTestResult(
                    success=True,
                    banner=banner[:500],
                    version=version[:500],
                    device_type_detected=self.device_type,
                    elapsed_ms=int((time.time() - t0) * 1000),
                )
            finally:
                self.disconnect()
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                error=str(e),
                device_type_detected=self.device_type,
                elapsed_ms=int((time.time() - t0) * 1000),
            )

    def _read_banner(self) -> str:
        """读 SSH banner（子类可覆盖）"""
        try:
            data = self.shell.recv(65535)
            return self.decode(data)
        except Exception:
            return ""

    @abc.abstractmethod
    def _read_version(self) -> str:
        """读设备版本号（子类必须实现）"""
        ...

    # ---------- 拉配置（公开 API） ----------

    def fetch_running_config(self) -> str:
        """拉全配置（SSH 抓 "show full-configuration" 之类）"""
        if not self._connected:
            self.connect()
        command, end_marker = self._config_command()
        self.shell.send(self.encode(command + "\n"))
        return self._recv_until(end_marker, idle_pause=0.3)

    @abc.abstractmethod
    def _config_command(self) -> Tuple[str, str]:
        """返回 (拉配置的命令, 终止标记)"""
        ...

    def _recv_until(self, end_marker: str, idle_pause: float = 0.3, max_wait: int = 60) -> str:
        """持续 recv 直到看到 end_marker 或超时"""
        buf = ""
        last_data_t = time.time()
        start_t = time.time()
        while time.time() - start_t < max_wait:
            try:
                self.shell.settimeout(0.5)
                chunk = self.shell.recv(65535)
                if chunk:
                    buf += self.decode(chunk)
                    last_data_t = time.time()
                    if end_marker and end_marker in buf:
                        # 多读一点确保拿完整
                        time.sleep(0.1)
                        try:
                            buf += self.decode(self.shell.recv(65535))
                        except Exception:
                            pass
                        break
            except Exception:
                # timeout: 检查 idle
                if time.time() - last_data_t > idle_pause * 3:
                    break
        # 清掉 --More-- / ---- More ---- 提示
        for marker in ["--More--", "---- More ----", "--- More ---"]:
            buf = buf.replace(marker, "")
        return buf

    # ---------- 解析（子类实现） ----------

    @abc.abstractmethod
    def parse_config(
        self, config_text: str
    ) -> Tuple[List[AddressObject], List[ServiceObject], List[FirewallPolicy]]:
        """解析配置文本 → (地址, 服务, 策略)"""
        ...

    # ---------- 命令生成（子类实现） ----------

    @abc.abstractmethod
    def generate_commands(
        self,
        new_policies: List[Dict[str, Any]],
        existing_addresses: List[AddressObject],
        existing_services: List[ServiceObject],
        existing_schedules: List[ScheduleObject],
    ) -> List[str]:
        """生成要推送的 CLI 命令"""
        ...

    # ---------- 推送（默认实现） ----------

    def push_commands(
        self, commands: List[str], progress_callback=None
    ) -> List[PushProgress]:
        """按行发送命令 + 错误检测

        progress_callback(seq, command, output, success, elapsed_ms) 可选
        """
        if not self._connected:
            self.connect()

        results: List[PushProgress] = []
        # 先进入配置模式（如果需要）
        preamble = self._push_preamble()
        if preamble:
            self.shell.send(self.encode(preamble + "\n"))
            time.sleep(0.2)
            self.shell.recv(65535)

        for seq, cmd in enumerate(commands, 1):
            t0 = time.time()
            try:
                self.shell.send(self.encode(cmd + "\n"))
                # 等待 prompt 回来
                output = self._wait_for_prompt(cmd, timeout=10)
                elapsed = int((time.time() - t0) * 1000)
                success, error = self._check_error(output, cmd)
                progress = PushProgress(
                    seq=seq,
                    command=cmd,
                    output=output,
                    success=success,
                    elapsed_ms=elapsed,
                    error=error,
                )
            except Exception as e:
                elapsed = int((time.time() - t0) * 1000)
                progress = PushProgress(
                    seq=seq, command=cmd, output="", success=False,
                    elapsed_ms=elapsed, error=str(e),
                )
            results.append(progress)
            if progress_callback:
                try:
                    progress_callback(progress)
                except Exception:
                    pass
            if not progress.success and self._is_fatal_error(progress.error):
                # 致命错误：中止
                break

        # 退出配置模式
        postamble = self._push_postamble()
        if postamble:
            self.shell.send(self.encode(postamble + "\n"))
            time.sleep(0.2)
        return results

    def _push_preamble(self) -> str:
        """推送前的命令（如 sys / config terminal），默认空"""
        return ""

    def _push_postamble(self) -> str:
        """推送后的命令（如 exit / write），默认空"""
        return ""

    def _wait_for_prompt(self, sent_cmd: str, timeout: int = 10) -> str:
        """等设备 prompt 出现"""
        buf = ""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                self.shell.settimeout(0.3)
                chunk = self.shell.recv(65535)
                if chunk:
                    buf += self.decode(chunk)
                    # 各种 prompt
                    if buf.rstrip().endswith(("[H3C]", "]", ">", "#")):
                        return buf
            except Exception:
                pass
        return buf

    def _check_error(self, output: str, cmd: str) -> Tuple[bool, str]:
        """检查输出是否含错误"""
        lower = output.lower()
        for kw in ["% unknown command", "error:", "invalid", "syntax error",
                   "command rejected", "wrong parameters"]:
            if kw in lower and "date format error" not in lower:
                return False, f"含错误关键词 '{kw}': {output[:200]}"
        return True, ""

    def _is_fatal_error(self, error: str) -> bool:
        """是否中止后续命令（默认否）"""
        return False
