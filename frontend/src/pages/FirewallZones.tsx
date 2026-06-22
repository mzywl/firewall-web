/**
 * FirewallZone 管理页 (单防火墙)
 *
 * 设计对应 重构.md §1 spec:
 *   - FirewallZone 是 Firewall 的子资源 (one-to-many)
 *   - 每条 zone 包含: zone_name, protected_ips, connect_region
 *   - 旧的 local_zone_name / external_zone_name / internal_protected_ips / external_protected_ips
 *     字段全部删除, 取而代之的是这里的 N 条 zone 记录
 *
 * 路由:
 *   /firewalls/:id/zones              → 本页 (列表 + 内联新增)
 *   /firewalls/:id/zones/:zoneId/edit → 弹窗/抽屉编辑单条
 */
import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { ArrowLeft, Plus, Edit, Trash2, Server } from 'lucide-react';
import axios from 'axios';
import { toast } from '../lib/toast';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

interface Firewall {
  id: number;
  name: string;
  alias: string;
  belong_region: string;
}

interface FirewallZone {
  id: number;
  firewall_id: number;
  zone_name: string;
  protected_ips: string;
  connect_region: string;
  zone_role: 'internal' | 'external';  // 设计文档 §1: 显式 internal/external 角色
  created_at: string;
  updated_at: string;
}

type ZoneRole = 'internal' | 'external';

const EMPTY_ZONE: {
  zone_name: string;
  protected_ips: string;
  connect_region: string;
  zone_role: ZoneRole;
} = {
  zone_name: '',
  protected_ips: '',
  connect_region: '',
  zone_role: 'internal',  // 设计文档 §1: 默认 internal (Trust)
};

export default function FirewallZones() {
  const { id } = useParams<{ id: string }>();
  const firewallId = Number(id);

  const [firewall, setFirewall] = useState<Firewall | null>(null);
  const [zones, setZones] = useState<FirewallZone[]>([]);
  const [loading, setLoading] = useState(true);

  // 新增/编辑态
  const [showForm, setShowForm] = useState(false);
  const [editingZone, setEditingZone] = useState<FirewallZone | null>(null);
  const [formData, setFormData] = useState(EMPTY_ZONE);

  useEffect(() => {
    fetchFirewall();
    fetchZones();
  }, [firewallId]);

  const fetchFirewall = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/firewalls/${firewallId}`);
      setFirewall(res.data);
    } catch (error) {
      toast.apiError(error, '获取防火墙信息失败');
    }
  };

  const fetchZones = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_BASE_URL}/firewall-zones/firewall/${firewallId}`);
      setZones(res.data.zones || []);
    } catch (error) {
      toast.apiError(error, '获取安全域列表失败');
      setZones([]);
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingZone(null);
    setFormData({ ...EMPTY_ZONE, connect_region: firewall?.belong_region || '' });
    setShowForm(true);
  };

  const openEdit = (zone: FirewallZone) => {
    setEditingZone(zone);
    setFormData({
      zone_name: zone.zone_name,
      protected_ips: zone.protected_ips || '',
      connect_region: zone.connect_region,
      zone_role: zone.zone_role,  // 设计文档 §1: 预填显式角色
    });
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingZone) {
        await axios.put(`${API_BASE_URL}/firewall-zones/${editingZone.id}`, formData);
        toast.success('安全域已更新');
      } else {
        await axios.post(`${API_BASE_URL}/firewall-zones/`, { firewall_id: firewallId, ...formData });
        toast.success('安全域已创建');
      }
      setShowForm(false);
      fetchZones();
    } catch (error) {
      toast.apiError(error, '保存失败');
    }
  };

  const handleDelete = (zone: FirewallZone) => {
    toast.confirm(`确定要删除安全域「${zone.zone_name}」吗？`, {
      confirmText: '确认删除',
      onConfirm: async () => {
        try {
          await axios.delete(`${API_BASE_URL}/firewall-zones/${zone.id}`);
          toast.success('已删除');
          fetchZones();
        } catch (error) {
          toast.apiError(error, '删除失败');
        }
      },
    });
  };

  // 设计文档 §1: 显式 zone_role, 替代旧 connect_region 隐式判定
  // 显示用 zone_name 实际值 (用户自由命名), role 只决定颜色
  const roleBadge = (z: FirewallZone) => z.zone_role === 'internal'
    ? <Badge className="bg-blue-500" title="内部防护域">{z.zone_name} · 内部</Badge>
    : <Badge className="bg-orange-500" title="外部防护域">{z.zone_name} · 外部</Badge>;

  return (
    <div className="container mx-auto p-6 max-w-5xl">
      {/* 顶部导航 */}
      <div className="flex items-center gap-4 mb-6">
        <Link to={`/firewalls/${firewallId}`}>
          <Button variant="outline">
            <ArrowLeft className="w-4 h-4 mr-1" /> 返回防火墙
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Server className="w-6 h-6" />
            安全域管理
          </h1>
          {firewall && (
            <p className="text-sm text-gray-500 mt-1">
              {firewall.name} ({firewall.alias || '无别名'}) · 所属大区:
              <Badge className="ml-2">{firewall.belong_region || '(未设)'}</Badge>
            </p>
          )}
        </div>
      </div>

      <Card className="p-6 mb-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">所有安全域 ({zones.length})</h2>
          <Button onClick={openCreate}>
            <Plus className="w-4 h-4 mr-1" /> 新增安全域
          </Button>
        </div>

        {loading ? (
          <p className="text-sm text-gray-500">加载中...</p>
        ) : zones.length === 0 ? (
          <p className="text-sm text-gray-500 py-8 text-center">
            暂无安全域。请点击右上角「新增安全域」配置。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-2 text-left">zone 名称</th>
                  <th className="px-4 py-2 text-left">连接大区</th>
                  <th className="px-4 py-2 text-left">属性</th>
                  <th className="px-4 py-2 text-left">保护 IP 段 (preview)</th>
                  <th className="px-4 py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {zones.map((zone) => (
                  <tr key={zone.id} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono font-medium">{zone.zone_name}</td>
                    <td className="px-4 py-2">
                      <Badge>{zone.connect_region || '(未设)'}</Badge>
                    </td>
                    <td className="px-4 py-2">
                      {roleBadge(zone)}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-600 max-w-md truncate">
                      {zone.protected_ips
                        ? zone.protected_ips.split('\n').slice(0, 2).join(', ') +
                          (zone.protected_ips.split('\n').length > 2 ? '...' : '')
                        : '(无)'}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button variant="outline" size="sm" onClick={() => openEdit(zone)}>
                        <Edit className="w-3 h-3" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="ml-2 text-red-600"
                        onClick={() => handleDelete(zone)}
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

      {/* 提示卡片 */}
      <Card className="p-4 bg-blue-50 border-blue-200">
        <h3 className="text-sm font-semibold mb-1">💡 配置说明</h3>
        <ul className="text-xs text-gray-700 space-y-1">
          <li>• 每个 zone 是防火墙上的一个物理接口 (Trust / Untrust / DMZ 等)</li>
          <li>• <b>connect_region</b>: 该 zone 物理上连接的大区, 仅作为参考 (历史字段, 已不直接判定 internal/external)</li>
          <li>• <b>zone_role</b> (设计文档 §1): 显式标记 internal/external, chain_planner 优先用这个判定</li>
          <li>• <b>protected_ips</b>: 该 zone 保护的 IP 网段 (每行一个 CIDR), 策略匹配用</li>
          <li>• 一个防火墙可以配多个 zone (e.g. Trust + DMZ + Untrust)</li>
          <li>• 跨大区访问的 SNAT 池在 <Link to={`/firewalls/${firewallId}/access`} className="text-blue-600 underline">「跨区配置」</Link> 页面单独配</li>
        </ul>
      </Card>

      {/* 新增/编辑弹窗 */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-2xl p-6 m-4 bg-white max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold mb-4">
              {editingZone ? `编辑安全域 #${editingZone.id}` : '新增安全域'}
            </h2>
            <form onSubmit={handleSubmit}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-1">zone 名称 *</label>
                  <Input
                    required
                    value={formData.zone_name}
                    onChange={(e) => setFormData({ ...formData, zone_name: e.target.value })}
                    placeholder="如: Trust / Untrust / DMZ"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    防火墙上的物理接口名
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">连接大区 *</label>
                  <Input
                    required
                    value={formData.connect_region}
                    onChange={(e) => setFormData({ ...formData, connect_region: e.target.value })}
                    placeholder="如: 生产区 / 测试区 / 互联网"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    该 zone 物理上连接的大区名 (跟 firewall.belong_region 对比, 仅作为参考)
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">
                    zone 角色 *
                    <span className="text-xs text-gray-500 ml-2">(设计文档 §1: 内部防护 / 外部防护 二选一)</span>
                  </label>
                  <select
                    required
                    className="w-full px-3 py-2 border rounded-md"
                    value={formData.zone_role}
                    onChange={(e) => setFormData({ ...formData, zone_role: e.target.value as 'internal' | 'external' })}
                  >
                    <option value="internal">internal (内部防护域 — 保护自家资产, 来自本防火墙归属大区的方向)</option>
                    <option value="external">external (外部防护域 — 通往其他大区或墙的出口方向)</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    两个维度: <b>zone_name</b> 你自由命名 (Trust / Untrust / DMZ / 自定义均可),
                    <b>zone_role</b> 系统内部/外部语义 (决定 chain_planner 寻路方向)
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">保护 IP 段</label>
                  <textarea
                    className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                    rows={8}
                    value={formData.protected_ips}
                    onChange={(e) => setFormData({ ...formData, protected_ips: e.target.value })}
                    placeholder={`每行一个网段, 例如:\n10.5.81.0/24\n10.5.82.0/24\n10.5.83.0/24`}
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    策略匹配用 — 用于判定 IP 是否在该 zone 管辖范围
                  </p>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <Button type="submit">保存</Button>
                <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
                  取消
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}