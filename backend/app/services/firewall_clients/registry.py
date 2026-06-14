"""防火墙客户端工厂

按 firewall.type 字符串返回对应的 Client 类实例。
"""
from __future__ import annotations

from typing import Optional

from .base import FirewallClient
from .fortigate import FortigateClient
from .guanqun import GuanqunClient
from .h3c import H3CClient
from .sangfor import SangforClient


# 防火墙类型 → Client 类的映射
_REGISTRY: dict = {
    "h3c": H3CClient,
    "fortigate": FortigateClient,
    "feita": FortigateClient,        # 飞塔 = fortigate 别名
    "guanqun": GuanqunClient,
    "sangfor": SangforClient,         # 深信服（已实现）
    "wangshen": SangforClient,        # 网神（已实现，跟深信服类似）
    # 以下暂未实现（无源码）:
    # "huawei": NotImplemented,
    # "shanshi": NotImplemented,
    # "leadsec": NotImplemented,
    # "hillstone": NotImplemented,
    # "other": NotImplemented,
}


def get_client_class(device_type: str):
    """根据设备类型返回 Client 类，找不到抛 NotImplementedError"""
    key = (device_type or "").lower()
    if key not in _REGISTRY:
        supported = ", ".join(sorted(set(_REGISTRY.keys())))
        raise NotImplementedError(
            f"设备类型 '{device_type}' 暂未实现 (已支持: {supported})"
        )
    return _REGISTRY[key]


def create_client(
    device_type: str,
    host: str,
    username: str,
    password: str,
    port: int = 22,
    timeout: int = 30,
    **kwargs,
) -> FirewallClient:
    """创建并返回 client 实例（不连接）"""
    cls = get_client_class(device_type)
    return cls(
        host=host,
        username=username,
        password=password,
        port=port,
        timeout=timeout,
        device_type=device_type,
        **kwargs,
    )


def supported_types() -> list:
    """返回已支持的设备类型列表"""
    return sorted(set(_REGISTRY.keys()))
