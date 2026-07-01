"""
app/services/firewall_clients/registry.py
设备客户端工厂

按 firewall.type 返回对应厂商的 Netmiko 客户端实现
"""
from typing import Type

from app.services.firewall_clients.base import NetmikoFirewallClient
from app.services.firewall_clients.h3c import H3CNetmikoClient
# 以后增加新品牌就在这里 import + 注册
# from app.services.firewall_clients.hillstone import HillstoneNetmikoClient
# from app.services.firewall_clients.sangfor import SangforNetmikoClient

# 注册表: db.fw_type 枚举值 → 客户端类
_REGISTRY: dict[str, Type[NetmikoFirewallClient]] = {
    "h3c": H3CNetmikoClient,
    # "hillstone": HillstoneNetmikoClient,
}


def get_client_class(device_type: str) -> Type[NetmikoFirewallClient]:
    """根据设备类型返回 Client 类，找不到抛 NotImplementedError"""
    key = (device_type or "").lower()
    if key not in _REGISTRY:
        supported = ", ".join(sorted(_REGISTRY.keys())) or "(none)"
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
) -> NetmikoFirewallClient:
    """创建并返回 client 实例（不连接）

    device_type: db.fw_type 字符串 (e.g. "h3c")
    host:        设备管理 IP
    username/password: SSH 凭据（明文，由调用方先 decrypt）
    port/timeout: SSH 端口 / 超时秒数
    """
    cls = get_client_class(device_type)
    return cls(
        host=host,
        username=username,
        password=password,
        port=port,
        timeout=timeout,
        **kwargs,
    )


def supported_types() -> list[str]:
    """返回已支持的设备类型列表"""
    return sorted(_REGISTRY.keys())
