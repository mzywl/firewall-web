"""冠群防火墙客户端

跟飞塔很像，命令从 define 改成 config（运行时），define 用于完整配置。
参照旧版 /home/lishiyu/output/lishiyu/cx/冠群防火墙策略.py
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .base import (
    AddressObject,
    FirewallClient,
    FirewallPolicy,
    ServiceObject,
)
from .fortigate import FortigateClient


class GuanqunClient(FortigateClient):
    """冠群跟飞塔命令体系接近，复用其命令生成，只调整少量细节"""

    def _read_version(self) -> str:
        self.shell.send(self.encode("get system status\n"))
        return self._recv_until("#", idle_pause=0.5, max_wait=5)

    def _config_command(self) -> Tuple[str, str]:
        # 冠群用 display full-configuration
        return "display full-configuration", "define router multicast"
