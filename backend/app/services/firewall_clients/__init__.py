"""防火墙客户端（各厂家 SSH 连接的抽象 + 实现）

目录结构:
- base.py:        抽象基类，定义所有厂家共有的流程
- registry.py:    客户端工厂（按 firewall.type 返回对应 client）
- h3c.py:         H3C 实现（GB2312 编码、object-group 命令）
- fortigate.py:   飞塔实现（UTF-8、edit/set/end 命令）
- guanqun.py:     冠群实现（跟飞塔类似但命令不同）
- sangfor.py:     网神实现（security policy + append 命令）
"""
