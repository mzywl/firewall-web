import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Info, Edit, Trash2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';

interface Firewall {
  id: number;
  name: string;
  alias: string;
  type: string;
  region: string;
  zones: string[];
}

interface SavedConfig {
  id: number;
  source_zone: string;
  dest_zone: string;
  firewall_id: number;
  firewall_name: string;
  nat_type: string | null;
  created_at: string;
  updated_at: string;
}

interface AnalysisResult {
  source_zone: string;
  dest_zone: string;
  is_same_zone: boolean;
  need_nat: boolean;
  nat_type: string | null;
  recommended_firewall: {
    id: number;
    name: string;
    alias: string;
    region: string;
  } | null;
  source_firewalls: Array<{ id: number; name: string; alias: string }>;
  dest_firewalls: Array<{ id: number; name: string; alias: string }>;
}

export default function ZoneAccessConfig() {
  const navigate = useNavigate();
  const [firewalls, setFirewalls] = useState<Firewall[]>([]);
  const [savedConfigs, setSavedConfigs] = useState<SavedConfig[]>([]);
  const [sourceZone, setSourceZone] = useState('');
  const [destZone, setDestZone] = useState('');
  const [selectedFirewall, setSelectedFirewall] = useState<number | null>(null);
  const [natType, setNatType] = useState<string>('');
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingConfigId, setEditingConfigId] = useState<number | null>(null);

  useEffect(() => {
    loadFirewalls();
    loadSavedConfigs();
  }, []);

  const loadFirewalls = async () => {
    try {
      const response = await fetch('/api/zone-access/firewalls');
      const data = await response.json();
      setFirewalls(data.firewalls);
    } catch (error) {
      console.error('加载防火墙列表失败:', error);
      alert('加载防火墙列表失败');
    }
  };

  const loadSavedConfigs = async () => {
    try {
      const response = await fetch('/api/zone-access/configs');
      const data = await response.json();
      setSavedConfigs(data.configs);
    } catch (error) {
      console.error('加载配置列表失败:', error);
    }
  };

  const handleEdit = (config: SavedConfig) => {
    setSourceZone(config.source_zone);
    setDestZone(config.dest_zone);
    setSelectedFirewall(config.firewall_id);
    setNatType(config.nat_type || '');
    setEditingConfigId(config.id);
    // 滚动到表单
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (configId: number) => {
    if (!confirm('确定要删除这条配置吗？')) {
      return;
    }

    try {
      const response = await fetch(`/api/zone-access/configs/${configId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        alert('配置已删除');
        loadSavedConfigs();
      } else {
        alert('删除失败');
      }
    } catch (error) {
      console.error('删除失败:', error);
      alert('删除失败');
    }
  };

  const handleAnalyze = async () => {
    if (!sourceZone || !destZone) {
      alert('请输入源区域和目的区域');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `/api/zone-access/analyze?source_zone=${encodeURIComponent(sourceZone)}&dest_zone=${encodeURIComponent(destZone)}`,
        { method: 'POST' }
      );
      const data = await response.json();
      setAnalysisResult(data);

      // 自动选择推荐的防火墙
      if (data.recommended_firewall) {
        setSelectedFirewall(data.recommended_firewall.id);
      }

      // 自动设置NAT类型
      if (data.nat_type) {
        setNatType(data.nat_type);
      }
    } catch (error) {
      console.error('分析失败:', error);
      alert('分析失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 p-6">
      {/* 头部 */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate('/')}
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold">区域访问配置</h1>
          <p className="text-muted-foreground mt-1">
            配置源区域和目的区域的访问规则，系统自动判断是否需要NAT
          </p>
        </div>
      </div>

      {/* 配置表单 */}
      <Card>
        <CardHeader>
          <CardTitle>区域配置</CardTitle>
          <CardDescription>
            输入源区域和目的区域，系统将自动分析访问场景
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">源区域</label>
              <input
                type="text"
                value={sourceZone}
                onChange={(e) => setSourceZone(e.target.value)}
                placeholder="例如：生产区"
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">目的区域</label>
              <input
                type="text"
                value={destZone}
                onChange={(e) => setDestZone(e.target.value)}
                placeholder="例如：测试区"
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
          </div>

          <Button
            onClick={handleAnalyze}
            disabled={loading || !sourceZone || !destZone}
            className="w-full"
          >
            {loading ? '分析中...' : '分析访问场景'}
          </Button>
        </CardContent>
      </Card>

      {/* 分析结果 */}
      {analysisResult && (
        <>
          {/* 场景判断 */}
          <Card className={analysisResult.is_same_zone ? 'border-green-500 bg-green-50' : 'border-blue-500 bg-blue-50'}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Info className="h-5 w-5" />
                <CardTitle>场景判断</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {analysisResult.is_same_zone ? (
                <div className="space-y-2">
                  <p className="text-green-700 font-semibold">✅ 同区域访问</p>
                  <p className="text-sm text-green-600">
                    源区域和目的区域相同，不需要NAT转换
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-blue-700 font-semibold">🔄 跨区域访问</p>
                  <p className="text-sm text-blue-600">
                    源区域和目的区域不同，需要配置NAT转换
                  </p>
                  {analysisResult.need_nat && (
                    <p className="text-sm text-blue-600">
                      推荐NAT类型：<span className="font-semibold">{analysisResult.nat_type}</span>
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 防火墙选择 */}
          <Card>
            <CardHeader>
              <CardTitle>防火墙配置</CardTitle>
              <CardDescription>
                {analysisResult.recommended_firewall
                  ? `推荐使用：${analysisResult.recommended_firewall.name}`
                  : '请选择防火墙'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">选择防火墙</label>
                <select
                  value={selectedFirewall || ''}
                  onChange={(e) => setSelectedFirewall(Number(e.target.value))}
                  className="w-full px-3 py-2 border rounded-md"
                >
                  <option value="">请选择...</option>
                  {firewalls.map((fw) => (
                    <option key={fw.id} value={fw.id}>
                      {fw.name} {fw.alias && `(${fw.alias})`} - {fw.region}
                    </option>
                  ))}
                </select>
              </div>

              {!analysisResult.is_same_zone && (
                <div>
                  <label className="block text-sm font-medium mb-2">NAT类型</label>
                  <select
                    value={natType}
                    onChange={(e) => setNatType(e.target.value)}
                    className="w-full px-3 py-2 border rounded-md"
                  >
                    <option value="">无需NAT</option>
                    <option value="SNAT">SNAT（源地址转换）</option>
                    <option value="DNAT">DNAT（目的地址转换）</option>
                    <option value="BOTH">双向NAT</option>
                  </select>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 匹配的防火墙信息 */}
          {(analysisResult.source_firewalls.length > 0 || analysisResult.dest_firewalls.length > 0) && (
            <Card>
              <CardHeader>
                <CardTitle>区域匹配信息</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {analysisResult.source_firewalls.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">源区域所在防火墙：</p>
                    <div className="space-y-1">
                      {analysisResult.source_firewalls.map((fw) => (
                        <div key={fw.id} className="text-sm text-muted-foreground">
                          • {fw.name} {fw.alias && `(${fw.alias})`}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {analysisResult.dest_firewalls.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">目的区域所在防火墙：</p>
                    <div className="space-y-1">
                      {analysisResult.dest_firewalls.map((fw) => (
                        <div key={fw.id} className="text-sm text-muted-foreground">
                          • {fw.name} {fw.alias && `(${fw.alias})`}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* 保存按钮 */}
          <div className="flex justify-end gap-4">
            <Button
              variant="outline"
              onClick={() => {
                setSourceZone('');
                setDestZone('');
                setSelectedFirewall(null);
                setNatType('');
                setAnalysisResult(null);
              }}
            >
              重置
            </Button>
            <Button
              onClick={async () => {
                if (!selectedFirewall) {
                  alert('请选择防火墙');
                  return;
                }

                try {
                  const response = await fetch('/api/zone-access/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      source_zone: sourceZone,
                      dest_zone: destZone,
                      firewall_id: selectedFirewall,
                      nat_type: natType || null
                    })
                  });

                  const data = await response.json();
                  alert(data.message || '配置已保存');
                  
                  // 重新加载配置列表
                  loadSavedConfigs();
                  
                  // 重置表单
                  setSourceZone('');
                  setDestZone('');
                  setSelectedFirewall(null);
                  setNatType('');
                  setAnalysisResult(null);
                  setEditingConfigId(null);
                } catch (error) {
                  console.error('保存失败:', error);
                  alert('保存失败');
                }
              }}
              disabled={!selectedFirewall}
            >
              {editingConfigId ? '更新配置' : '保存配置'}
            </Button>
          </div>
        </>
      )}

      {/* 已保存的配置列表 */}
      {savedConfigs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>已保存的配置</CardTitle>
            <CardDescription>
              共 {savedConfigs.length} 条配置
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted">
                  <tr>
                    <th className="px-4 py-2 text-left">源区域</th>
                    <th className="px-4 py-2 text-left">目的区域</th>
                    <th className="px-4 py-2 text-left">防火墙</th>
                    <th className="px-4 py-2 text-left">NAT类型</th>
                    <th className="px-4 py-2 text-left">更新时间</th>
                    <th className="px-4 py-2 text-center">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {savedConfigs.map((config) => (
                    <tr key={config.id} className="border-t">
                      <td className="px-4 py-2">{config.source_zone}</td>
                      <td className="px-4 py-2">{config.dest_zone}</td>
                      <td className="px-4 py-2">{config.firewall_name}</td>
                      <td className="px-4 py-2">
                        {config.nat_type ? (
                          <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">
                            {config.nat_type}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">无需NAT</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {new Date(config.updated_at).toLocaleString('zh-CN')}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center justify-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleEdit(config)}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(config.id)}
                          >
                            <Trash2 className="h-4 w-4 text-red-500" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
