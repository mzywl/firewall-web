import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface Firewall {
  id: number;
  name: string;
  alias?: string;
  type: string;
  management_ip: string;
  connection_type: string;
  protected_ips?: string;
  supported_policy_types?: string[];
  auto_push: number;
  push_contact?: string;
  status: string;
  is_active: number;
  created_at: string;
  updated_at: string;
}

export default function FirewallManagement() {
  const navigate = useNavigate();
  const [firewalls, setFirewalls] = useState<Firewall[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterType, setFilterType] = useState<string>('');

  useEffect(() => {
    fetchFirewalls();
  }, [filterStatus, filterType]);

  const fetchFirewalls = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filterStatus) params.append('status', filterStatus);
      if (filterType) params.append('type', filterType);
      
      const response = await axios.get(`${API_BASE_URL}/firewalls?${params.toString()}`);
      setFirewalls(response.data);
    } catch (error) {
      console.error('获取防火墙列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定要删除这个防火墙配置吗？')) return;
    
    try {
      await axios.delete(`${API_BASE_URL}/firewalls/${id}`);
      fetchFirewalls();
    } catch (error) {
      console.error('删除失败:', error);
      alert('删除失败');
    }
  };

  const filteredFirewalls = firewalls.filter(fw => {
    const matchSearch = !searchTerm || 
      fw.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      fw.alias?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      fw.management_ip.includes(searchTerm);
    return matchSearch;
  });

  const getTypeLabel = (type: string) => {
    const typeMap: Record<string, string> = {
      'guanqun': '冠群',
      'h3c': 'H3C',
      'feita': '飞塔',
      'wangshen': '网神',
      'fortigate': 'Fortigate',
      'hillstone': '山石',
      'leadsec': '绿盟',
      'other': '其他'
    };
    return typeMap[type] || type;
  };

  const getConnectionTypeLabel = (type: string) => {
    const typeMap: Record<string, string> = {
      'ssh': 'SSH',
      'api': 'API',
      'cli': 'CLI工具',
      'manual': '手动'
    };
    return typeMap[type] || type;
  };

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">防火墙管理</h1>
        <Button onClick={() => navigate('/firewalls/new')}>
          新增防火墙
        </Button>
      </div>

      {/* 搜索和筛选 */}
      <Card className="mb-6 p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Input
            placeholder="搜索名称、别名或IP..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <select
            className="px-3 py-2 border rounded-md"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="">全部状态</option>
            <option value="enabled">启用</option>
            <option value="disabled">禁用</option>
          </select>
          <select
            className="px-3 py-2 border rounded-md"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="">全部类型</option>
            <option value="guanqun">冠群</option>
            <option value="h3c">H3C</option>
            <option value="feita">飞塔</option>
            <option value="wangshen">网神</option>
            <option value="fortigate">Fortigate</option>
            <option value="hillstone">山石</option>
            <option value="leadsec">绿盟</option>
            <option value="other">其他</option>
          </select>
          <Button variant="outline" onClick={fetchFirewalls}>
            刷新
          </Button>
        </div>
      </Card>

      {/* 防火墙列表 */}
      {loading ? (
        <div className="text-center py-12">加载中...</div>
      ) : filteredFirewalls.length === 0 ? (
        <Card className="p-12 text-center text-gray-500">
          暂无防火墙配置
        </Card>
      ) : (
        <div className="grid gap-4">
          {filteredFirewalls.map((fw) => (
            <Card key={fw.id} className="p-6">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-xl font-semibold">{fw.name}</h3>
                    {fw.alias && (
                      <span className="text-gray-500">({fw.alias})</span>
                    )}
                    <Badge variant={fw.status === 'enabled' ? 'success' : 'secondary'}>
                      {fw.status === 'enabled' ? '启用' : '禁用'}
                    </Badge>
                    <Badge variant="outline">{getTypeLabel(fw.type)}</Badge>
                    <Badge variant="outline">{getConnectionTypeLabel(fw.connection_type)}</Badge>
                  </div>
                  
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-gray-600 mb-3">
                    <div>
                      <span className="font-medium">管理IP:</span> {fw.management_ip}
                    </div>
                    <div>
                      <span className="font-medium">自动推送:</span> {fw.auto_push ? '是' : '否'}
                    </div>
                    {fw.push_contact && (
                      <div>
                        <span className="font-medium">责任人:</span> {fw.push_contact}
                      </div>
                    )}
                    <div>
                      <span className="font-medium">策略类型:</span> {fw.supported_policy_types?.join(', ') || '未设置'}
                    </div>
                  </div>

                  {fw.protected_ips && (
                    <details className="text-sm">
                      <summary className="cursor-pointer text-blue-600 hover:text-blue-800">
                        查看防护IP段 ({fw.protected_ips.split('\n').filter(Boolean).length}个)
                      </summary>
                      <pre className="mt-2 p-3 bg-gray-50 rounded text-xs overflow-auto max-h-40">
                        {fw.protected_ips}
                      </pre>
                    </details>
                  )}
                </div>

                <div className="flex gap-2 ml-4">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/firewalls/${fw.id}/edit`)}
                  >
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => handleDelete(fw.id)}
                  >
                    删除
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
