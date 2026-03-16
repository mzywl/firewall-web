import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';

interface NATInfo {
  need_nat: boolean;
  nat_type: 'SNAT' | 'DNAT' | 'BOTH' | null;
  snat_address: string | null;
  dnat_address: string | null;
  source_zone: string | null;
  dest_zone: string | null;
  warnings: string[];
}

interface NATPolicy {
  type: 'SNAT' | 'DNAT';
  source_zone: string;
  source_ip: string;
  dest_zone: string;
  dest_ip: string;
  service: string;
  action: string;
}

interface Policy {
  id: number;
  source_zone: string;
  source_ip: string;
  dest_zone: string;
  dest_ip: string;
  service: string;
  action: string;
  nat_info: NATInfo;
  nat_policies: NATPolicy[];
  not_pushed_reason?: string;
}

interface Firewall {
  id: number;
  name: string;
  alias: string;
  type: string;
  management_ip: string;
  region: string;
  auto_push: number;
  push_contact: string;
}

interface FirewallGroup {
  firewall: Firewall;
  policies: Policy[];
}

interface PreviewData {
  order: {
    id: number;
    order_no: string;
    title: string;
    status: string;
    created_at: string;
  };
  firewalls: FirewallGroup[];
  not_pushed_policies: Policy[];
  warnings: string[];
  errors: string[];
}

export const Preview = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoExecute, setAutoExecute] = useState<Record<number, boolean>>({});

  useEffect(() => {
    loadPreviewData();
  }, [orderId]);

  const loadPreviewData = async () => {
    try {
      setLoading(true);
      const response = await fetch(`http://localhost:8000/api/workorders/${orderId}/preview`);
      if (!response.ok) {
        throw new Error('加载预览数据失败');
      }
      const data = await response.json();
      setPreviewData(data);
      
      // 初始化自动执行状态（默认全部勾选）
      const initialAutoExecute: Record<number, boolean> = {};
      data.firewall_groups.forEach((group: FirewallGroup) => {
        if (group.firewall.auto_push === 1) {
          initialAutoExecute[group.firewall.id] = true;
        }
      });
      setAutoExecute(initialAutoExecute);
    } catch (error) {
      console.error('加载预览数据失败:', error);
      alert('加载预览数据失败');
    } finally {
      setLoading(false);
    }
  };

  const toggleAutoExecute = (firewallId: number) => {
    setAutoExecute(prev => ({
      ...prev,
      [firewallId]: !prev[firewallId]
    }));
  };

  const handleNext = () => {
    // 保存自动执行配置到 localStorage
    localStorage.setItem(`preview_auto_execute_${orderId}`, JSON.stringify(autoExecute));
    navigate(`/order/${orderId}/push`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-lg">加载中...</div>
      </div>
    );
  }

  if (!previewData) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-lg text-red-500">加载失败</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6 p-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate(`/order/${orderId}/edit`)}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">策略预览</h1>
            <p className="text-muted-foreground mt-1">
              {previewData.order.title} · 工单号: {previewData.order.order_no}
            </p>
          </div>
        </div>
        <Button onClick={handleNext} size="lg">
          下一步：推送策略
        </Button>
      </div>

      {/* 警告和错误提示 */}
      {(previewData.warnings.length > 0 || previewData.errors.length > 0 || previewData.unmatched_policies.length > 0) && (
        <Card className="border-yellow-500 bg-yellow-50">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-600" />
              <CardTitle className="text-yellow-800">异常提示</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {previewData.errors.length > 0 && (
              <div>
                <div className="font-semibold text-red-600 mb-1">错误：</div>
                <ul className="list-disc list-inside space-y-1">
                  {previewData.errors.map((error, idx) => (
                    <li key={idx} className="text-sm text-red-600">{error}</li>
                  ))}
                </ul>
              </div>
            )}
            {previewData.warnings.length > 0 && (
              <div>
                <div className="font-semibold text-yellow-700 mb-1">警告：</div>
                <ul className="list-disc list-inside space-y-1">
                  {previewData.warnings.map((warning, idx) => (
                    <li key={idx} className="text-sm text-yellow-700">{warning}</li>
                  ))}
                </ul>
              </div>
            )}
            {previewData.unmatched_policies.length > 0 && (
              <div>
                <div className="font-semibold text-orange-600 mb-1">
                  未匹配防火墙的策略（{previewData.unmatched_policies.length} 条）：
                </div>
                <div className="border rounded-lg overflow-hidden mt-2">
                  <table className="w-full text-sm">
                    <thead className="bg-orange-100">
                      <tr>
                        <th className="px-4 py-2 text-left w-16">序号</th>
                        <th className="px-4 py-2 text-left">源IP</th>
                        <th className="px-4 py-2 text-left">目的IP</th>
                        <th className="px-4 py-2 text-left">服务/端口</th>
                        <th className="px-4 py-2 text-left">原因</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewData.unmatched_policies.map((policy) => (
                        <tr key={policy.id} className="border-t">
                          <td className="px-4 py-2 font-semibold text-center">{policy.sequence}</td>
                          <td className="px-4 py-2 whitespace-pre-line">{policy.source_ip}</td>
                          <td className="px-4 py-2 whitespace-pre-line">{policy.dest_ip}</td>
                          <td className="px-4 py-2 whitespace-pre-line">{policy.service}</td>
                          <td className="px-4 py-2 text-orange-600">{policy.not_pushed_reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 防火墙分组展示 */}
      {previewData.firewall_groups.map((group) => (
        <Card key={group.firewall.id}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-xl">
                  {group.firewall.name}
                  {group.firewall.alias && (
                    <span className="text-sm text-muted-foreground ml-2">({group.firewall.alias})</span>
                  )}
                </CardTitle>
                <CardDescription className="mt-1">
                  类型: {group.firewall.type} | 管理IP: {group.firewall.management_ip} | 
                  区域: {group.firewall.region || '未设置'} | 
                  责任人: {group.firewall.push_contact || '未设置'}
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoExecute[group.firewall.id] || false}
                    onChange={() => toggleAutoExecute(group.firewall.id)}
                    className="w-4 h-4"
                  />
                  <span className="text-sm">自动执行</span>
                </label>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-muted-foreground mb-3">
              共 {group.policies.length} 条策略
            </div>
            
            {/* 策略表格 */}
            <div className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted">
                  <tr>
                    <th className="px-4 py-2 text-left w-16">序号</th>
                    <th className="px-4 py-2 text-left">源区域</th>
                    <th className="px-4 py-2 text-left">源IP</th>
                    <th className="px-4 py-2 text-left">目的区域</th>
                    <th className="px-4 py-2 text-left">目的IP</th>
                    <th className="px-4 py-2 text-left">服务/端口</th>
                    <th className="px-4 py-2 text-left">动作</th>
                    <th className="px-4 py-2 text-left">NAT</th>
                  </tr>
                </thead>
                <tbody>
                  {group.policies.map((policy) => (
                    <React.Fragment key={policy.id || policy.original_policy_id}>
                      {/* 原始策略行 */}
                      <tr key={policy.id} className="border-t hover:bg-muted/50">
                        <td className="px-4 py-2 font-semibold text-center">{policy.sequence}</td>
                        <td className="px-4 py-2">{policy.source_zone}</td>
                        <td className="px-4 py-2 whitespace-pre-line">{policy.source_ip}</td>
                        <td className="px-4 py-2">{policy.dest_zone}</td>
                        <td className="px-4 py-2 whitespace-pre-line">{policy.dest_ip}</td>
                        <td className="px-4 py-2 whitespace-pre-line">{policy.service}</td>
                        <td className="px-4 py-2">{policy.action}</td>
                        <td className="px-4 py-2">
                          {policy.nat_info.need_nat ? (
                            <div className="flex items-center gap-1">
                              <Info className="h-4 w-4 text-blue-500" />
                              <span className="text-blue-600 font-medium">
                                {policy.nat_info.nat_type}
                              </span>
                            </div>
                          ) : (
                            <span className="text-gray-400">无需NAT</span>
                          )}
                        </td>
                      </tr>
                      
                      {/* NAT转换后的策略行 */}
                      {policy.nat_policies.map((natPolicy, idx) => (
                        <tr key={`${policy.id}-nat-${idx}`} className="border-t bg-blue-50">
                          <td className="px-4 py-2"></td>
                          <td className="px-4 py-2 text-blue-700">{natPolicy.source_zone}</td>
                          <td className="px-4 py-2 text-blue-700 whitespace-pre-line">
                            {natPolicy.source_ip}
                            {natPolicy.type === 'SNAT' && (
                              <span className="ml-2 px-2 py-0.5 bg-blue-200 text-blue-800 text-xs rounded">
                                [SNAT]
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2 text-blue-700">{natPolicy.dest_zone}</td>
                          <td className="px-4 py-2 text-blue-700 whitespace-pre-line">
                            {natPolicy.dest_ip}
                            {natPolicy.type === 'DNAT' && (
                              <span className="ml-2 px-2 py-0.5 bg-green-200 text-green-800 text-xs rounded">
                                [DNAT]
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2 text-blue-700 whitespace-pre-line">{natPolicy.service}</td>
                          <td className="px-4 py-2 text-blue-700">{natPolicy.action}</td>
                          <td className="px-4 py-2">
                            <span className="text-xs text-blue-600">转换后</span>
                          </td>
                        </tr>
                      ))}
                      
                      {/* NAT警告 */}
                      {policy.nat_info.warnings.length > 0 && (
                        <tr className="border-t bg-yellow-50">
                          <td colSpan={8} className="px-4 py-2">
                            <div className="flex items-start gap-2">
                              <AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5" />
                              <div className="text-sm text-yellow-700">
                                {policy.nat_info.warnings.join('; ')}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ))}

      {/* 底部操作按钮 */}
      <div className="flex justify-end gap-4">
        <Button
          variant="outline"
          onClick={() => navigate(`/order/${orderId}/edit`)}
        >
          返回编辑
        </Button>
        <Button onClick={handleNext} size="lg">
          下一步：推送策略
        </Button>
      </div>
    </div>
  );
};
