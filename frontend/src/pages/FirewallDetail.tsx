/**
 * Firewall 详情页 (查看 + 子页面入口)
 *
 * 设计:
 *   - 只读展示防火墙基本信息
 *   - 列出 zones 和 access configs 计数 + 入口链接
 *   - 编辑按钮 → /firewalls/:id/edit
 *   - 子页面:
 *     - /firewalls/:id/zones   (FirewallZones)
 *     - /firewalls/:id/access  (FirewallAccessConfigs)
 */
import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { ArrowLeft, Edit, Server, Network, Layers } from 'lucide-react';
import axios from 'axios';
import { toast } from '../lib/toast';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

interface Firewall {
  id: number;
  name: string;
  alias: string;
  type: string;
  management_ip: string;
  belong_region: string;
  connection_type: string;
  connection_config: any;
  is_zone_boundary: number;
  auto_push: number;
  status: string;
  is_active: number;
  created_at: string;
  updated_at: string;
}

export default function FirewallDetail() {
  const { id } = useParams<{ id: string }>();
  const firewallId = Number(id);

  const [firewall, setFirewall] = useState<Firewall | null>(null);
  const [zonesCount, setZonesCount] = useState(0);
  const [accessConfigsCount, setAccessConfigsCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchFirewall();
    fetchCounts();
  }, [firewallId]);

  const fetchFirewall = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_BASE_URL}/firewalls/${firewallId}`);
      setFirewall(res.data);
    } catch (error) {
      toast.apiError(error, '获取防火墙信息失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchCounts = async () => {
    try {
      const zonesRes = await axios.get(`${API_BASE_URL}/firewall-zones/firewall/${firewallId}`);
      setZonesCount((zonesRes.data.zones || []).length);
    } catch (error) {
      setZonesCount(0);
    }
    try {
      const cfgRes = await axios.get(`${API_BASE_URL}/zone-access/configs`);
      const all = (cfgRes.data.configs || []) as any[];
      setAccessConfigsCount(all.filter((c) => c.firewall_id === firewallId).length);
    } catch (error) {
      setAccessConfigsCount(0);
    }
  };

  if (loading || !firewall) {
    return (
      <div className="container mx-auto p-6 max-w-5xl">
        <p className="text-sm text-gray-500">加载中...</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 max-w-5xl">
      <div className="flex items-center gap-4 mb-6">
        <Link to="/firewalls">
          <Button variant="outline">
            <ArrowLeft className="w-4 h-4 mr-1" /> 返回列表
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-3xl font-bold flex items-center gap-2">
            {firewall.name}
            {firewall.status === 'enabled' ? (
              <Badge>启用</Badge>
            ) : (
              <Badge variant="outline">禁用</Badge>
            )}
            {firewall.is_zone_boundary === 1 && (
              <Badge className="bg-orange-500">边界墙</Badge>
            )}
          </h1>
          {firewall.alias && (
            <p className="text-sm text-gray-500 mt-1">{firewall.alias}</p>
          )}
        </div>
        <Link to={`/firewalls/${firewallId}/edit`}>
          <Button>
            <Edit className="w-4 h-4 mr-1" /> 编辑基本信息
          </Button>
        </Link>
      </div>

      {/* 基本信息卡片 */}
      <Card className="p-6 mb-4">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Server className="w-5 h-5" />
          基本信息
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="防火墙类型" value={firewall.type.toUpperCase()} />
          <Field label="管理 IP" value={firewall.management_ip} mono />
          <Field label="所属大区" value={firewall.belong_region || '(未设)'} />
          <Field label="连接类型" value={firewall.connection_type.toUpperCase()} />
          <Field label="自动推送" value={firewall.auto_push === 1 ? '是' : '否'} />
          <Field
            label="创建时间"
            value={firewall.created_at ? new Date(firewall.created_at).toLocaleString('zh-CN') : '-'}
          />
        </div>
      </Card>

      {/* 子页面入口卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <Link to={`/firewalls/${firewallId}/zones`}>
          <Card className="p-6 hover:bg-gray-50 cursor-pointer transition-colors h-full">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold flex items-center gap-2 mb-2">
                  <Layers className="w-5 h-5 text-blue-500" />
                  安全域 (FirewallZone)
                </h3>
                <p className="text-sm text-gray-600">
                  管理防火墙的物理 zone (Trust / Untrust / DMZ 等),
                  每条 zone 包含连接大区和保护 IP 段
                </p>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-blue-600">{zonesCount}</div>
                <div className="text-xs text-gray-500">条 zone</div>
              </div>
            </div>
            <div className="mt-4 text-sm text-blue-600">→ 进入管理</div>
          </Card>
        </Link>

        <Link to={`/firewalls/${firewallId}/access`}>
          <Card className="p-6 hover:bg-gray-50 cursor-pointer transition-colors h-full">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold flex items-center gap-2 mb-2">
                  <Network className="w-5 h-5 text-orange-500" />
                  跨区配置 (ZoneAccessConfig)
                </h3>
                <p className="text-sm text-gray-600">
                  管理跨大区访问路径, 每条 cfg 表达一对 source_region → dest_region
                  的边界 NAT (boundary zone + SNAT 池)
                </p>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-orange-600">{accessConfigsCount}</div>
                <div className="text-xs text-gray-500">条 cfg</div>
              </div>
            </div>
            <div className="mt-4 text-sm text-orange-600">→ 进入管理</div>
          </Card>
        </Link>
      </div>

      {/* 连接配置 (只读) */}
      {firewall.connection_config && Object.keys(firewall.connection_config).length > 0 && (
        <Card className="p-6 mb-4">
          <h2 className="text-lg font-semibold mb-4">连接配置 (脱敏后)</h2>
          <pre className="bg-gray-50 p-4 rounded text-xs overflow-auto">
            {JSON.stringify(firewall.connection_config, null, 2)}
          </pre>
          <p className="text-xs text-gray-500 mt-2">
            密码已加密存储, 此处展示的为加密后值
          </p>
        </Card>
      )}
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-sm ${mono ? 'font-mono' : ''}`}>{value || '(未设)'}</div>
    </div>
  );
}