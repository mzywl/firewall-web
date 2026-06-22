/**
 * FirewallAccessConfigs 管理页 (单防火墙)
 *
 * 设计对应 重构.md §1 spec:
 *   - ZoneAccessConfig 是 Firewall 的子资源 (one-to-many)
 *   - 每条 cfg 表达一对 (source_region → dest_region) 的边界 NAT 路径
 *   - 字段: source_region, dest_region, boundary_source_zone, boundary_dest_zone, need_nat, snat_pool
 *   - 旧的 outbound_snat_pool / inbound_snat_pool 字段已删除 (合并到 cfg.snat_pool, 按方向区分)
 *
 * 路由:
 *   /firewalls/:id/access              → 本页 (列表 + 内联新增)
 *   /firewalls/:id/access/:cfgId/edit → 弹窗编辑
 */
import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { ArrowLeft, Plus, Edit, Trash2, Network } from 'lucide-react';
import axios from 'axios';
import { toast } from '../lib/toast';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

interface Firewall {
  id: number;
  name: string;
  alias: string;
  belong_region: string;
  is_zone_boundary: number;
}

interface ZoneAccessConfig {
  id: number;
  firewall_id: number;
  source_region: string;
  dest_region: string;
  boundary_source_zone: string;
  boundary_dest_zone: string;
  need_nat: number;
  snat_pool: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

interface FirewallZone {
  zone_name: string;
  connect_region: string;
}

const EMPTY_CFG = {
  source_region: '',
  dest_region: '',
  boundary_source_zone: '',
  boundary_dest_zone: '',
  need_nat: 0,
  snat_pool: '',
  description: '',
};

export default function FirewallAccessConfigs() {
  const { id } = useParams<{ id: string }>();
  const firewallId = Number(id);

  const [firewall, setFirewall] = useState<Firewall | null>(null);
  const [configs, setConfigs] = useState<ZoneAccessConfig[]>([]);
  const [availableZones, setAvailableZones] = useState<FirewallZone[]>([]);
  const [loading, setLoading] = useState(true);

  const [showForm, setShowForm] = useState(false);
  const [editingCfg, setEditingCfg] = useState<ZoneAccessConfig | null>(null);
  const [formData, setFormData] = useState(EMPTY_CFG);

  useEffect(() => {
    fetchFirewall();
    fetchConfigs();
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

  const fetchConfigs = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_BASE_URL}/zone-access/configs`);
      const all = res.data.configs || [];
      setConfigs(all.filter((c: ZoneAccessConfig) => c.firewall_id === firewallId));
    } catch (error) {
      toast.apiError(error, '获取跨区配置列表失败');
      setConfigs([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchZones = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/firewall-zones/firewall/${firewallId}`);
      setAvailableZones(
        (res.data.zones || []).map((z: any) => ({
          zone_name: z.zone_name,
          connect_region: z.connect_region,
        })),
      );
    } catch (error) {
      // 非关键, 允许空列表
    }
  };

  const openCreate = () => {
    setEditingCfg(null);
    setFormData(EMPTY_CFG);
    setShowForm(true);
  };

  const openEdit = (cfg: ZoneAccessConfig) => {
    setEditingCfg(cfg);
    setFormData({
      source_region: cfg.source_region,
      dest_region: cfg.dest_region,
      boundary_source_zone: cfg.boundary_source_zone,
      boundary_dest_zone: cfg.boundary_dest_zone,
      need_nat: cfg.need_nat,
      snat_pool: cfg.snat_pool || '',
      description: cfg.description || '',
    });
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingCfg) {
        await axios.put(`${API_BASE_URL}/zone-access/configs/${editingCfg.id}`, formData);
        toast.success('跨区配置已更新');
      } else {
        await axios.post(`${API_BASE_URL}/zone-access/save`, {
          ...formData,
          firewall_id: firewallId,
        });
        toast.success('跨区配置已创建');
      }
      setShowForm(false);
      fetchConfigs();
    } catch (error) {
      toast.apiError(error, '保存失败');
    }
  };

  const handleDelete = (cfg: ZoneAccessConfig) => {
    const label = `${cfg.source_region} → ${cfg.dest_region}`;
    toast.confirm(`确定要删除跨区配置「${label}」吗？`, {
      confirmText: '确认删除',
      onConfirm: async () => {
        try {
          await axios.delete(`${API_BASE_URL}/zone-access/configs/${cfg.id}`);
          toast.success('已删除');
          fetchConfigs();
        } catch (error) {
          toast.apiError(error, '删除失败');
        }
      },
    });
  };

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      {/* 顶部导航 */}
      <div className="flex items-center gap-4 mb-6">
        <Link to={`/firewalls/${firewallId}`}>
          <Button variant="outline">
            <ArrowLeft className="w-4 h-4 mr-1" /> 返回防火墙
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Network className="w-6 h-6" />
            跨区配置管理
          </h1>
          {firewall && (
            <p className="text-sm text-gray-500 mt-1">
              {firewall.name} ({firewall.alias || '无别名'})
              {firewall.is_zone_boundary === 1 ? (
                <Badge className="ml-2">边界墙</Badge>
              ) : (
                <Badge variant="outline" className="ml-2">非边界墙 (此处配置通常为空)</Badge>
              )}
            </p>
          )}
        </div>
      </div>

      <Card className="p-6 mb-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">
            跨大区路径 ({configs.length})
          </h2>
          <Button onClick={openCreate}>
            <Plus className="w-4 h-4 mr-1" /> 新增跨区配置
          </Button>
        </div>

        {loading ? (
          <p className="text-sm text-gray-500">加载中...</p>
        ) : configs.length === 0 ? (
          <p className="text-sm text-gray-500 py-8 text-center">
            暂无跨区配置。如需配置源大区 → 目的大区 的 SNAT 路径,请点击右上角新增。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-2 text-left">源大区 → 目的大区</th>
                  <th className="px-4 py-2 text-left">边界 zone (源→目的)</th>
                  <th className="px-4 py-2 text-center">SNAT</th>
                  <th className="px-4 py-2 text-left">SNAT 池</th>
                  <th className="px-4 py-2 text-left">备注</th>
                  <th className="px-4 py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {configs.map((cfg) => (
                  <tr key={cfg.id} className="border-b hover:bg-gray-50">
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-1">
                        <Badge>{cfg.source_region}</Badge>
                        <span className="text-gray-400">→</span>
                        <Badge variant="outline">{cfg.dest_region}</Badge>
                      </div>
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">
                      {cfg.boundary_source_zone} → {cfg.boundary_dest_zone}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {cfg.need_nat === 1 ? (
                        <Badge className="bg-orange-500">需要</Badge>
                      ) : (
                        <Badge variant="outline">不需要</Badge>
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-gray-700 max-w-xs truncate">
                      {cfg.snat_pool || '(无)'}
                    </td>
                    <td className="px-4 py-2 text-xs text-gray-500 max-w-xs truncate">
                      {cfg.description || '-'}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Button variant="outline" size="sm" onClick={() => openEdit(cfg)}>
                        <Edit className="w-3 h-3" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="ml-2 text-red-600"
                        onClick={() => handleDelete(cfg)}
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
      <Card className="p-4 bg-amber-50 border-amber-200">
        <h3 className="text-sm font-semibold mb-1">⚠️ 配置说明</h3>
        <ul className="text-xs text-gray-700 space-y-1">
          <li>• 每条 cfg 表达一对 (源大区 → 目的大区) 的边界 NAT 路径</li>
          <li>• <b>boundary_source_zone</b> / <b>boundary_dest_zone</b>: 这台边界墙上对应的物理 zone 名 (来自 <Link to={`/firewalls/${firewallId}/zones`} className="text-blue-600 underline">安全域管理</Link>)</li>
          <li>• <b>need_nat=1</b>: 跨区时需要 SNAT (出向换 src, 入向换 src)</li>
          <li>• <b>snat_pool</b>: SNAT 地址池 (如 192.168.1.1-1.8 或 SNAT_POOL_NAME), 出向入向共用一个池</li>
          <li>• 已有 zone 名建议从下拉选择, 避免拼写错:</li>
        </ul>
        {availableZones.length > 0 && (
          <div className="mt-2 text-xs">
            <b>本防火墙可用 zone:</b>
            {availableZones.map((z) => (
              <Badge key={z.zone_name} variant="outline" className="ml-2">
                {z.zone_name} ({z.connect_region})
              </Badge>
            ))}
          </div>
        )}
      </Card>

      {/* 新增/编辑弹窗 */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-3xl p-6 m-4 bg-white max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-semibold mb-4">
              {editingCfg ? `编辑跨区配置 #${editingCfg.id}` : '新增跨区配置'}
            </h2>
            <form onSubmit={handleSubmit}>
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">源大区 *</label>
                    <Input
                      required
                      value={formData.source_region}
                      onChange={(e) => setFormData({ ...formData, source_region: e.target.value })}
                      placeholder="如: 生产区"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">目的大区 *</label>
                    <Input
                      required
                      value={formData.dest_region}
                      onChange={(e) => setFormData({ ...formData, dest_region: e.target.value })}
                      placeholder="如: 测试区"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      boundary_source_zone *
                      <span className="text-xs text-gray-500 ml-2">(面向源大区的本地 zone)</span>
                    </label>
                    {availableZones.length > 0 ? (
                      <select
                        required
                        className="w-full px-3 py-2 border rounded-md font-mono"
                        value={formData.boundary_source_zone}
                        onChange={(e) => setFormData({ ...formData, boundary_source_zone: e.target.value })}
                      >
                        <option value="">-- 选择 zone --</option>
                        {availableZones.map((z) => (
                          <option key={z.zone_name} value={z.zone_name}>
                            {z.zone_name} ({z.connect_region})
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        required
                        value={formData.boundary_source_zone}
                        onChange={(e) => setFormData({ ...formData, boundary_source_zone: e.target.value })}
                        placeholder="先在安全域管理页配 zone"
                      />
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">
                      boundary_dest_zone *
                      <span className="text-xs text-gray-500 ml-2">(面向目的大区的本地 zone)</span>
                    </label>
                    {availableZones.length > 0 ? (
                      <select
                        required
                        className="w-full px-3 py-2 border rounded-md font-mono"
                        value={formData.boundary_dest_zone}
                        onChange={(e) => setFormData({ ...formData, boundary_dest_zone: e.target.value })}
                      >
                        <option value="">-- 选择 zone --</option>
                        {availableZones.map((z) => (
                          <option key={z.zone_name} value={z.zone_name}>
                            {z.zone_name} ({z.connect_region})
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        required
                        value={formData.boundary_dest_zone}
                        onChange={(e) => setFormData({ ...formData, boundary_dest_zone: e.target.value })}
                        placeholder="先在安全域管理页配 zone"
                      />
                    )}
                  </div>
                </div>
                <div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.need_nat === 1}
                      onChange={(e) => setFormData({ ...formData, need_nat: e.target.checked ? 1 : 0 })}
                      className="w-4 h-4"
                    />
                    <span className="text-sm font-medium">此跨区路径需要 SNAT</span>
                  </label>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">SNAT 地址池</label>
                  <textarea
                    className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                    rows={3}
                    value={formData.snat_pool}
                    onChange={(e) => setFormData({ ...formData, snat_pool: e.target.value })}
                    placeholder={`地址段或地址池名称, 例如:\n10.5.1.1-10.5.1.10\n或: SNAT_POOL_PROD`}
                    disabled={formData.need_nat === 0}
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    出向入向共用此池 (按物理方向决定语义)
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">备注</label>
                  <textarea
                    className="w-full px-3 py-2 border rounded-md"
                    rows={2}
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  />
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