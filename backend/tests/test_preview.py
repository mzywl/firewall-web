"""
测试预览API
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, Base, engine
from app.models import Order, Policy, Firewall, OrderStatus, FirewallType, ConnectionType
from sqlalchemy.orm import Session

client = TestClient(app)


def setup_test_data(db: Session):
    """创建测试数据"""
    # 创建防火墙
    firewall = Firewall(
        name="测试防火墙",
        alias="TEST-FW",
        type=FirewallType.fortigate,
        management_ip="192.168.1.1",
        region="生产区",
        local_zone_name="internal",
        external_zone_name="external",
        connection_type=ConnectionType.ssh,
        internal_protected_ips="10.0.0.0/8\n172.16.0.0/12",
        external_protected_ips="192.168.0.0/16",
        outbound_snat_pool="200.1.1.1-200.1.1.10",
        inbound_dnat_pool="200.2.2.1-200.2.2.10",
        auto_push=1,
        push_contact="测试管理员",
        is_active=1
    )
    db.add(firewall)
    db.commit()
    db.refresh(firewall)
    
    # 创建工单
    order = Order(
        order_no="TEST-001",
        title="测试工单",
        description="测试预览功能",
        status=OrderStatus.pending,
        created_by="测试用户"
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    
    # 创建策略（跨区域，需要NAT）
    policy1 = Policy(
        order_id=order.id,
        firewall_id=firewall.id,
        source_zone="生产区",
        source_ip="10.0.1.100",
        dest_zone="测试区",
        dest_ip="192.168.1.100",
        service="TCP/80",
        action="permit"
    )
    db.add(policy1)
    
    # 创建策略（同区域，不需要NAT）
    policy2 = Policy(
        order_id=order.id,
        firewall_id=firewall.id,
        source_zone="生产区",
        source_ip="10.0.1.101",
        dest_zone="生产区",
        dest_ip="10.0.2.100",
        service="TCP/443",
        action="permit"
    )
    db.add(policy2)
    
    db.commit()
    
    return order.id, firewall.id


def test_preview_api():
    """测试预览API"""
    # 创建测试数据库
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    order_id, firewall_id = setup_test_data(db)
    
    # 调用预览API
    response = client.get(f"/api/workorders/{order_id}/preview")
    
    assert response.status_code == 200
    data = response.json()
    
    # 验证返回结构
    assert "order" in data
    assert "firewall_groups" in data
    assert "unmatched_policies" in data
    assert "warnings" in data
    assert "errors" in data
    
    # 验证工单信息
    assert data["order"]["id"] == order_id
    assert data["order"]["order_no"] == "TEST-001"
    
    # 验证防火墙分组
    assert len(data["firewall_groups"]) > 0
    group = data["firewall_groups"][0]
    assert group["firewall"]["id"] == firewall_id
    assert len(group["policies"]) == 2
    
    # 验证NAT分析
    policy_with_nat = [p for p in group["policies"] if p["nat_info"]["need_nat"]]
    assert len(policy_with_nat) > 0
    
    # 清理测试数据
    db.query(Policy).delete()
    db.query(Order).delete()
    db.query(Firewall).delete()
    db.commit()
    db.close()


if __name__ == "__main__":
    test_preview_api()
    print("✅ 预览API测试通过")
