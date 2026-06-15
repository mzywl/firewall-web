import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

interface ConnectionConfig {
  type?: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  base_url?: string;
  token?: string;
  auth_type?: string;
  tool_path?: string;
  config_template?: string;
}

interface FormData {
  name: string;
  alias: string;
  type: string;
  management_ip: string;
  
  // 区域信息
  region: string;
  local_zone_name: string;
  external_zone_name: string;
  
  // 连接方式
  connection_type: string;
  connection_config: ConnectionConfig;
  
  // 防护范围（分内部和外部）
  internal_protected_ips: string;
  external_protected_ips: string;
  is_zone_boundary: number;

  // NAT配置（仅当 is_zone_boundary=1 时由 UI 显示和填写）
  outbound_snat_pool: string;
  inbound_dnat_pool: string;
  inbound_snat_pool: string;
  outbound_dnat_pool: string;
  
  // 推送配置
  auto_push: number;
  allow_same_firewall_push: number;
  push_contact: string;
  push_remark: string;
  status: string;
  remark: string;
}

export default function FirewallForm() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;

  const [formData, setFormData] = useState<FormData>({
    name: '',
    alias: '',
    type: 'h3c',
    management_ip: '',
    
    region: '',
    local_zone_name: '',
    external_zone_name: '',
    
    connection_type: 'ssh',
    connection_config: {},
    
    internal_protected_ips: '',
    external_protected_ips: '',
    is_zone_boundary: 0,

    outbound_snat_pool: '',
    inbound_dnat_pool: '',
    inbound_snat_pool: '',
    outbound_dnat_pool: '',
    
    auto_push: 1,
    allow_same_firewall_push: 0,
    push_contact: '',
    push_remark: '',
    status: 'enabled',
    remark: ''
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
        is_zone_boundary: data.is_zone_boundary ?? 0,
        connection_config: data.connection_config || {}
      });
    } catch (error) {
      console.error('获取防火墙信息失败:', error);
      alert('获取防火墙信息失败');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      // 转换枚举值为小写
      const submitData = {
        ...formData,
        type: formData.type.toLowerCase(),
        connection_type: formData.connection_type.toLowerCase()
      };
      
      console.log('=== 提交数据 ===', submitData);
      console.log('type:', submitData.type);
      console.log('connection_type:', submitData.connection_type);
      
      if (isEdit) {
        await axios.put(`${API_BASE_URL}/firewalls/${id}`, submitData);
        alert('更新成功');
      } else {
        await axios.post(`${API_BASE_URL}/firewalls`, submitData);
        alert('创建成功');
      }
      navigate('/firewalls');
    } catch (error) {
      console.error('保存失败:', error);
      alert('保存失败');
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
              <label className="block text-sm font-medium mb-1">主机地址</label>
              <Input
                value={formData.connection_config.host || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, host: e.target.value }
                })}
                placeholder="如: 10.5.51.33"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">端口</label>
              <Input
                type="number"
                value={formData.connection_config.port || 22}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, port: parseInt(e.target.value) }
                })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">用户名</label>
              <Input
                value={formData.connection_config.username || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, username: e.target.value }
                })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">密码</label>
              <Input
                type="password"
                value={formData.connection_config.password || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, password: e.target.value }
                })}
                placeholder={isEdit ? '留空表示不修改' : ''}
              />
            </div>
          </>
        );
      
      case 'api':
        return (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">API地址</label>
              <Input
                value={formData.connection_config.base_url || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, base_url: e.target.value }
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
                  connection_config: { ...formData.connection_config, username: e.target.value }
                })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">密码</label>
              <Input
                type="password"
                value={formData.connection_config.password || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, password: e.target.value }
                })}
                placeholder={isEdit ? '留空表示不修改' : ''}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Token（可选）</label>
              <Input
                type="password"
                value={formData.connection_config.token || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, token: e.target.value }
                })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">认证方式</label>
              <select
                className="w-full px-3 py-2 border rounded-md"
                value={formData.connection_config.auth_type || 'basic'}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, auth_type: e.target.value }
                })}
              >
                <option value="basic">Basic Auth（账号密码）</option>
                <option value="bearer">Bearer Token</option>
                <option value="apikey">API Key</option>
              </select>
            </div>
          </>
        );
      
      case 'cli':
        return (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">工具路径</label>
              <Input
                value={formData.connection_config.tool_path || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, tool_path: e.target.value }
                })}
                placeholder="如: /usr/bin/firewall-cli"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium mb-1">参数模板</label>
              <Input
                value={formData.connection_config.config_template || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  connection_config: { ...formData.connection_config, config_template: e.target.value }
                })}
                placeholder="如: --host {ip} --user {user}"
              />
            </div>
          </>
        );
      
      case 'manual':
        return (
          <div className="col-span-3 text-sm text-gray-600">
            手动模式不需要配置连接信息，请在下方填写推送责任人。
          </div>
        );
      
      default:
        return null;
    }
  };

  return (
    <div className="container mx-auto p-6 max-w-4xl">
      <div className="flex items-center gap-4 mb-6">
        <Button variant="outline" onClick={() => navigate('/firewalls')}>
          返回
        </Button>
        <h1 className="text-3xl font-bold">
          {isEdit ? '编辑防火墙' : '新增防火墙'}
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
              <label className="block text-sm font-medium mb-1">简称/别名</label>
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
                <option value="shanshi">山石</option>
                <option value="guanqun">冠群</option>
                <option value="feita">飞塔</option>
                <option value="wangshen">网神</option>
                <option value="fortigate">Fortigate</option>
                <option value="hillstone">Hillstone</option>
                <option value="leadsec">绿盟</option>
                <option value="other">其他</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">管理IP *</label>
              <Input
                required
                value={formData.management_ip}
                onChange={(e) => setFormData({ ...formData, management_ip: e.target.value })}
                placeholder="如: 10.5.51.33"
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
                connection_type: e.target.value,
                connection_config: {}
              })}
            >
              <option value="ssh">SSH</option>
              <option value="api">API</option>
              <option value="cli">CLI工具</option>
              <option value="manual">手动</option>
            </select>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {renderConnectionConfig()}
          </div>
        </Card>

        <Card className="p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">区域信息</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">所属区域</label>
              <Input
                value={formData.region}
                onChange={(e) => setFormData({ ...formData, region: e.target.value })}
                placeholder="如: 小营数据中心"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">本地防护区域名称</label>
              <Input
                value={formData.local_zone_name}
                onChange={(e) => setFormData({ ...formData, local_zone_name: e.target.value })}
                placeholder="如: 服务器区"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">外部防护区域名称</label>
              <Input
                value={formData.external_zone_name}
                onChange={(e) => setFormData({ ...formData, external_zone_name: e.target.value })}
                placeholder="如: 互联网区"
              />
            </div>
          </div>
        </Card>

        <Card className="p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">防护范围</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">内部防护IP段</label>
              <textarea
                className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                rows={6}
                value={formData.internal_protected_ips}
                onChange={(e) => setFormData({ ...formData, internal_protected_ips: e.target.value })}
                placeholder="每行一个IP段，如:&#10;10.5.81.0/24&#10;10.5.82.0/24&#10;10.5.83.0/24"
              />
              <p className="text-xs text-gray-500 mt-1">
                内部网络IP段，用于匹配策略源IP
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">外部防护IP段</label>
              <textarea
                className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                rows={6}
                value={formData.external_protected_ips}
                onChange={(e) => setFormData({ ...formData, external_protected_ips: e.target.value })}
                placeholder="每行一个IP段，如:&#10;10.247.0.0/24&#10;10.247.1.0/24"
              />
              <p className="text-xs text-gray-500 mt-1">
                外部网络IP段，用于匹配策略目的IP
              </p>
            </div>
            <div className="md:col-span-2">
              <label className="flex items-center gap-2 cursor-pointer p-3 bg-amber-50 border border-amber-200 rounded-md">
                <input
                  type="checkbox"
                  checked={formData.is_zone_boundary === 1}
                  onChange={(e) => setFormData({ ...formData, is_zone_boundary: e.target.checked ? 1 : 0 })}
                  className="w-4 h-4"
                />
                <div>
                  <span className="text-sm font-medium">是否区域边界防火墙</span>
                  <p className="text-xs text-gray-500 mt-0.5">
                    勾选后下方会出现"默认入向/出向 SNAT 地址组名称"配置。仅跨区域流量需要 NAT 转换的边界防火墙需勾选。
                  </p>
                </div>
              </label>
            </div>
          </div>
        </Card>

        {formData.is_zone_boundary === 1 && (
        <Card className="p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">NAT 配置（仅边界防火墙）</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">出向SNAT地址段/地址池</label>
              <textarea
                className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                rows={3}
                value={formData.outbound_snat_pool}
                onChange={(e) => setFormData({ ...formData, outbound_snat_pool: e.target.value })}
                placeholder="地址段或地址池名称，如:&#10;10.5.1.1-10.5.1.10&#10;或: SNAT_POOL_1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">入向DNAT地址段/地址池</label>
              <textarea
                className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                rows={3}
                value={formData.inbound_dnat_pool}
                onChange={(e) => setFormData({ ...formData, inbound_dnat_pool: e.target.value })}
                placeholder="地址段或地址池名称"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">入向SNAT地址段/地址池</label>
              <textarea
                className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                rows={3}
                value={formData.inbound_snat_pool}
                onChange={(e) => setFormData({ ...formData, inbound_snat_pool: e.target.value })}
                placeholder="地址段或地址池名称"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">出向DNAT地址段/地址池</label>
              <textarea
                className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                rows={3}
                value={formData.outbound_dnat_pool}
                onChange={(e) => setFormData({ ...formData, outbound_dnat_pool: e.target.value })}
                placeholder="地址段或地址池名称"
              />
            </div>
          </div>
        </Card>
        )}

        <Card className="p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">推送配置</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
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
            <div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.allow_same_firewall_push === 1}
                  onChange={(e) => setFormData({ ...formData, allow_same_firewall_push: e.target.checked ? 1 : 0 })}
                  className="w-4 h-4"
                />
                <span className="text-sm font-medium">同墙推送（源目的IP都在内部IP段时是否推送）</span>
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">推送责任人</label>
              <Input
                value={formData.push_contact}
                onChange={(e) => setFormData({ ...formData, push_contact: e.target.value })}
                placeholder="如: 张三"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium mb-1">推送备注</label>
              <textarea
                className="w-full px-3 py-2 border rounded-md"
                rows={3}
                value={formData.push_remark}
                onChange={(e) => setFormData({ ...formData, push_remark: e.target.value })}
                placeholder="特殊说明..."
              />
            </div>
          </div>
        </Card>

        <Card className="p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">其他</h2>
          <div>
            <label className="block text-sm font-medium mb-1">备注</label>
            <textarea
              className="w-full px-3 py-2 border rounded-md"
              rows={3}
              value={formData.remark}
              onChange={(e) => setFormData({ ...formData, remark: e.target.value })}
              placeholder="其他备注信息..."
            />
          </div>
        </Card>

        <div className="flex gap-4">
          <Button type="submit" disabled={loading}>
            {loading ? '保存中...' : '保存'}
          </Button>
          <Button type="button" variant="outline" onClick={() => navigate('/firewalls')}>
            取消
          </Button>
        </div>
      </form>
    </div>
  );
}
