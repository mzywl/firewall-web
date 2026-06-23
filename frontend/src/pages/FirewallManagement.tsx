/**
 * 防火墙管理 (列表)
 *
 * 设计对应 重构.md §1 spec:
 *   - 字段: name, alias, type, management_ip, belong_region (was region), connection_type,
 *           is_zone_boundary, auto_push, status, is_active
 *   - 删字段 (历史): covered_region, local_zone_name, external_zone_name, internal_protected_ips,
 *             external_protected_ips, outbound_snat_pool, inbound_snat_pool,
 *             allow_same_firewall_push, push_contact, push_remark, supported_policy_types, remark
 *
 * 计数列 (C5 改造):
 *   - 安全域: 调 GET /api/firewall-zones/all 聚合端点 (替代之前的 N+1)
 *   - 跨区配置: 调 GET /api/zone-access/configs 全量 + 前端 forEach
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { Plus, Edit, Trash2, Layers, Network, ExternalLink } from 'lucide-react';
import axios from 'axios';
import { toast } from '../lib/toast';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

interface Firewall {
  id: number;
  name: string;
  alias: string | null;
  type: string;
  management_ip: string;
  belong_region: string | null;
  connection_type: string;
  is_zone_boundary: number;
  auto_push: number;
  status: string;
  is_active: number;
  created_at: string;
  updated_at: string;
  // 计数 (前端额外拉)
  zones_count?: number;
  access_configs_count?: number;
}

export default function FirewallManagement() {
  const [firewalls, setFirewalls] = useState<Firewall[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterRegion, setFilterRegion] = useState<string>('');

  useEffect(() => {
    fetchFirewalls();
  }, [filterStatus]);

  const fetchFirewalls = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filterStatus) params.append('status', filterStatus);

      const [fwRes, zonesRes, cfgRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/firewalls?${params.toString()}`),
        // C5: 改用 /firewall-zones/all 聚合端点 (C2 后端加的), 替代 /firewall/0 拉全表 + 前端 forEach
        // - 后端: SELECT firewall_id, COUNT(*) GROUP BY firewall_id, 一次返回 {firewall_id, zone_count}[]
        // - 前端: 直接 O(1) hashmap 查, 不用再 forEach 计数
        axios.get(`${API_BASE_URL}/firewall-zones/all`).catch(() => ({ data: { firewall_zones: [] } })),
        axios.get(`${API_BASE_URL}/zone-access/configs`).catch(() => ({ data: { configs: [] } })),
      ]);

      const firewallList: Firewall[] = Array.isArray(fwRes.data) ? fwRes.data : [];

      // 统计 zones 计数 (直接 hashmap, 不用 forEach)
      const zonesCountByFw: Record<number, number> = {};
      (zonesRes.data.firewall_zones || []).forEach((z: { firewall_id: number; zone_count: number }) => {
        zonesCountByFw[z.firewall_id] = z.zone_count;
      });

      // 统计 access configs 计数
      const cfgCountByFw: Record<number, number> = {};
      (cfgRes.data.configs || []).forEach((c: any) => {
        cfgCountByFw[c.firewall_id] = (cfgCountByFw[c.firewall_id] || 0) + 1;
      });

      setFirewalls(
        firewallList.map((fw) => ({
          ...fw,
          zones_count: zonesCountByFw[fw.id] || 0,
          access_configs_count: cfgCountByFw[fw.id] || 0,
        })),
      );
    } catch (error) {
      toast.apiError(error, '获取防火墙列表失败');
      setFirewalls([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = (fw: Firewall) => {
    toast.confirm(`确定要删除防火墙「${fw.name}」吗？关联的策略会一并删除。`, {
      confirmText: '确认删除',
      onConfirm: async () => {
        try {
          await axios.delete(`${API_BASE_URL}/firewalls/${fw.id}`);
          toast.success('已删除');
          fetchFirewalls();
        } catch (error) {
          toast.apiError(error, '删除失败');
        }
      },
    });
  };

  // 收集所有大区 (用于 filter)
  const allRegions = Array.from(
    new Set(firewalls.map((f) => f.belong_region).filter(Boolean)),
  ).sort();

  const filteredFirewalls = firewalls.filter((fw) => {
    const matchSearch =
      !searchTerm ||
      fw.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      fw.alias?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      fw.management_ip.includes(searchTerm);
    const matchRegion = !filterRegion || fw.belong_region === filterRegion;
    return matchSearch && matchRegion;
  });

  return (
    <div className="container mx-auto p-6 max-w-7xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold">防火墙管理</h1>
          <p className="text-sm text-gray-500 mt-1">
            共 {firewalls.length} 台防火墙 ({filteredFirewalls.length} 条匹配)
          </p>
        </div>
        <Link to="/firewalls/new">
          <Button>
            <Plus className="w-4 h-4 mr-1" /> 新增防火墙
          </Button>
        </Link>
      </div>

      <Card className="p-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <Input
              placeholder="🔍 搜索名称 / 别名 / IP..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <div>
            <select
              className="w-full px-3 py-2 border rounded-md"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
            >
              <option value="">全部状态</option>
              <option value="enabled">启用</option>
              <option value="disabled">禁用</option>
            </select>
          </div>
          <div>
            <select
              className="w-full px-3 py-2 border rounded-md"
              value={filterRegion}
              onChange={(e) => setFilterRegion(e.target.value)}
            >
              <option value="">全部大区</option>
              {allRegions.map((r) => (
                <option key={r!} value={r!}>
                  {r}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden">
        {loading ? (
          <p className="text-sm text-gray-500 p-8 text-center">加载中...</p>
        ) : filteredFirewalls.length === 0 ? (
          <p className="text-sm text-gray-500 p-8 text-center">
            没有匹配的防火墙
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left">名称</th>
                  <th className="px-4 py-3 text-left">类型</th>
                  <th className="px-4 py-3 text-left">管理 IP</th>
                  <th className="px-4 py-3 text-left">所属大区</th>
                  <th className="px-4 py-3 text-center">边界墙</th>
                  <th className="px-4 py-3 text-center">
                    <Layers className="w-4 h-4 inline" /> 安全域
                  </th>
                  <th className="px-4 py-3 text-center">
                    <Network className="w-4 h-4 inline" /> 跨区配置
                  </th>
                  <th className="px-4 py-3 text-center">状态</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredFirewalls.map((fw) => (
                  <tr key={fw.id} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <Link to={`/firewalls/${fw.id}`} className="font-medium hover:text-blue-600">
                        {fw.name}
                        {fw.alias && (
                          <span className="text-gray-500 text-xs ml-2">({fw.alias})</span>
                        )}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-mono">{fw.type.toUpperCase()}</td>
                    <td className="px-4 py-3 font-mono text-xs">{fw.management_ip}</td>
                    <td className="px-4 py-3">
                      {fw.belong_region ? (
                        <Badge variant="outline">{fw.belong_region}</Badge>
                      ) : (
                        <span className="text-gray-400 text-xs">未设</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {fw.is_zone_boundary === 1 ? (
                        <Badge className="bg-orange-500">是</Badge>
                      ) : (
                        <span className="text-gray-400 text-xs">否</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Link
                        to={`/firewalls/${fw.id}/zones`}
                        className="inline-flex items-center gap-1 text-blue-600 hover:underline"
                      >
                        {fw.zones_count}
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Link
                        to={`/firewalls/${fw.id}/access`}
                        className="inline-flex items-center gap-1 text-orange-600 hover:underline"
                      >
                        {fw.access_configs_count}
                        <ExternalLink className="w-3 h-3" />
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {fw.status === 'enabled' ? (
                        <Badge>启用</Badge>
                      ) : (
                        <Badge variant="outline">禁用</Badge>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link to={`/firewalls/${fw.id}/edit`}>
                        <Button variant="outline" size="sm">
                          <Edit className="w-3 h-3" />
                        </Button>
                      </Link>
                      <Button
                        variant="outline"
                        size="sm"
                        className="ml-2 text-red-600"
                        onClick={() => handleDelete(fw)}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="p-4 mt-4 bg-blue-50 border-blue-200">
        <h3 className="text-sm font-semibold mb-1">💡 新设计要点</h3>
        <ul className="text-xs text-gray-700 space-y-1">
          <li>• <b>安全域</b> 和 <b>跨区配置</b> 不再是防火墙的 inline 字段, 改为独立子页面管理</li>
          <li>• 点表格里的 <Layers className="inline w-3 h-3" /> 列数字跳到该防火墙的安全域列表</li>
          <li>• 点 <Network className="inline w-3 h-3" /> 列数字跳到该防火墙的跨区配置列表</li>
          <li>• 点名称跳到详情页 (基本信息 + 子页面入口)</li>
        </ul>
      </Card>
    </div>
  );
}