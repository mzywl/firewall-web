/**
 * Firewall 基本信息表单 (新建 / 编辑)
 *
 * 设计对应 重构.md §1 spec:
 *   - 只编辑 Firewall 表本身的字段 (基本信息 + connection)
 *   - 不含 zone / protected_ips / SNAT 池 / 推送配置 — 这些迁到独立的子页面
 *   - 字段映射:
 *       region → belong_region
 *       local_zone_name / external_zone_name / internal_protected_ips / external_protected_ips /
 *       outbound_snat_pool / inbound_snat_pool / allow_same_firewall_push / push_contact /
 *       push_remark / remark / supported_policy_types  → 全部删除
 *
 * 子页面入口:
 *   - /firewalls/:id/zones   → 管理 FirewallZone (zone_name, protected_ips, connect_region)
 *   - /firewalls/:id/access  → 管理 ZoneAccessConfig (boundary_*, need_nat, snat_pool)
 */
import { useState, useEffect } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import axios from 'axios';
import { toast } from '../lib/toast';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

interface ConnectionConfig {
  type?: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  base_url?: string;
  token?: string;
}

interface FormData {
  name: string;
  alias: string;
  type: string;
  management_ip: string;
  belong_region: string;
  connection_type: 'ssh' | 'api';
  connection_config: ConnectionConfig;
  is_zone_boundary: number;
  auto_push: number;
  status: string;
}

export default function BasicFirewallForm() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;

  const [formData, setFormData] = useState<FormData>({
    name: '',
    alias: '',
    type: 'h3c',
    management_ip: '',
    belong_region: '',
    connection_type: 'ssh',
    connection_config: {},
    is_zone_boundary: 0,
    auto_push: 1,
    status: 'enabled',
  });

  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isEdit) {
      fetchFirewall();
    }
  }, [id]);

  const fetchFirewall = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/firewalls/${id}`);
      const data = response.data;
      setFormData({
        ...data,
        // 防御性默认值
        is_zone_boundary: data.is_zone_boundary ?? 0,
        auto_push: data.auto_push ?? 1,
        connection_type: (data.connection_type || 'ssh') as 'ssh' | 'api',
        connection_config: data.connection_config || {},
      });
    } catch (error) {
      toast.apiError(error, '获取防火墙信息失败');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const submitData = {
        ...formData,
        type: formData.type.toLowerCase(),
        connection_type: formData.connection_type.toLowerCase(),
      };

      if (isEdit) {
        await axios.put(`${API_BASE_URL}/firewalls/${id}`, submitData);
        toast.success('更新成功');
      } else {
        const created = await axios.post(`${API_BASE_URL}/firewalls`, submitData);
        toast.success('创建成功');
        // 创建后跳到详情页让用户继续配置 zones 和 access configs
        if (created.data?.id) {
          navigate(`/firewalls/${created.data.id}`);
          return;
        }
      }
      navigate('/firewalls');
    } catch (error) {
      toast.apiError(error, '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const renderConnectionConfig = () => {
    switch (formData.connection_type) {
      case 'ssh':
        return (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">主机地址 *</label>
              <Input
                value={formData.connection_config.host || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, host: e.target.value },
                })}
                placeholder="如: 10.5.51.33"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">SSH 端口</label>
              <Input
                type="number"
                value={formData.connection_config.port || 22}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, port: parseInt(e.target.value) },
                })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">用户名 *</label>
              <Input
                value={formData.connection_config.username || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, username: e.target.value },
                })}
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium mb-1">密码</label>
              <Input
                type="password"
                value={formData.connection_config.password || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, password: e.target.value },
                })}
                placeholder={isEdit ? '留空表示不修改' : ''}
              />
            </div>
          </>
        );

      case 'api':
        return (
          <>
            <div className="col-span-2">
              <label className="block text-sm font-medium mb-1">API 地址 *</label>
              <Input
                value={formData.connection_config.base_url || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, base_url: e.target.value },
                })}
                placeholder="如: https://firewall.example.com/api"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">用户名</label>
              <Input
                value={formData.connection_config.username || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, username: e.target.value },
                })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">密码 / Token</label>
              <Input
                type="password"
                value={formData.connection_config.password || formData.connection_config.token || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: {
                    ...formData.connection_config,
                    password: e.target.value,
                    token: e.target.value,
                  },
                })}
              />
            </div>
          </>
        );

      default:
        return null;
    }
  };

  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <div className="flex items-center gap-4 mb-6">
        <Button variant="outline" onClick={() => navigate('/firewalls')}>
          返回列表
        </Button>
        <h1 className="text-3xl font-bold">
          {isEdit ? `编辑防火墙 #${id}` : '新增防火墙'}
        </h1>
      </div>

      <form onSubmit={handleSubmit}>
        <Card className="p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">基础信息</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">防火墙名称 *</label>
              <Input
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="如: 小营数据中心总部服务器防火墙"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">简称 / 别名</label>
              <Input
                value={formData.alias}
                onChange={(e) => setFormData({ ...formData, alias: e.target.value })}
                placeholder="如: 小营总部"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">防火墙类型 *</label>
              <select
                required
                className="w-full px-3 py-2 border rounded-md"
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
              >
                <option value="h3c">H3C</option>
                <option value="huawei">华为</option>
                <option value="sangfor">深信服</option>
                <option value="hillstone">Hillstone</option>
                <option value="fortigate">Fortigate</option>
                <option value="other">其他</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">管理 IP *</label>
              <Input
                required
                value={formData.management_ip}
                onChange={(e) => setFormData({ ...formData, management_ip: e.target.value })}
                placeholder="如: 10.5.51.33"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                所属大区
                <span className="text-xs text-gray-500 ml-2">(组织归属, 用于按 region 匹配防火墙)</span>
              </label>
              <Input
                value={formData.belong_region}
                onChange={(e) => setFormData({ ...formData, belong_region: e.target.value })}
                placeholder="如: 小营数据中心 / 测试区"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">状态</label>
              <select
                className="w-full px-3 py-2 border rounded-md"
                value={formData.status}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
              >
                <option value="enabled">启用</option>
                <option value="disabled">禁用</option>
              </select>
            </div>
          </div>
        </Card>

        <Card className="p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">连接方式</h2>
          <div className="mb-4">
            <label className="block text-sm font-medium mb-1">连接类型 *</label>
            <select
              required
              className="w-full px-3 py-2 border rounded-md"
              value={formData.connection_type}
              onChange={(e) => setFormData({
                ...formData,
                connection_type: e.target.value as 'ssh' | 'api',
                connection_config: {},
              })}
            >
              <option value="ssh">SSH</option>
              <option value="api">API</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              项目已精简连接方式 (重构.md §1), 仅保留 ssh / api 两种
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {renderConnectionConfig()}
          </div>
        </Card>

        <Card className="p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">推送配置</h2>
          <div className="space-y-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_zone_boundary === 1}
                onChange={(e) => setFormData({ ...formData, is_zone_boundary: e.target.checked ? 1 : 0 })}
                className="w-4 h-4"
              />
              <span className="text-sm font-medium">区域边界防火墙</span>
              <span className="text-xs text-gray-500 ml-2">
                (勾选后可在「跨区配置」页面配置 boundary zone + SNAT 池)
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.auto_push === 1}
                onChange={(e) => setFormData({ ...formData, auto_push: e.target.checked ? 1 : 0 })}
                className="w-4 h-4"
              />
              <span className="text-sm font-medium">支持自动推送</span>
            </label>
          </div>
        </Card>

        <div className="flex gap-4">
          <Button type="submit" disabled={loading}>
            {loading ? '保存中...' : '保存'}
          </Button>
          <Button type="button" variant="outline" onClick={() => navigate('/firewalls')}>
            取消
          </Button>
          {isEdit && (
            <div className="ml-auto flex gap-2">
              <Link to={`/firewalls/${id}/zones`}>
                <Button type="button" variant="outline">管理安全域 →</Button>
              </Link>
              <Link to={`/firewalls/${id}/access`}>
                <Button type="button" variant="outline">管理跨区配置 →</Button>
              </Link>
            </div>
          )}
        </div>
      </form>
    </div>
  );
}