import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, FileCode } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { UnmatchedPoliciesTable } from '../components/preview/UnmatchedPoliciesTable';
import { FirewallPolicyTable } from '../components/preview/FirewallPolicyTable';
import { PushScriptModal } from '../components/preview/PushScriptModal';
import { toast } from '../lib/toast';
import type {
  FirewallGroup,
  PreviewData,
  PreviewFirewall,
} from '../types';

// 注: 旧的 NATInfo / NATPolicy / Policy / Firewall / FirewallGroup / PreviewData
// 5 个本地 interface 已抽到 types/preview.ts (P1 类型统一)
// 剩下 2 个 (FirewallGroup / PreviewData) 在本文件直接引用, 通过 import 拿
// NATInfo / NATPolicy / Policy / Firewall 通过 PreviewPolicy.nested 间接使用, 不需要顶层 import

export const Preview = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoExecute, setAutoExecute] = useState<Record<number, boolean>>({});
  const [scriptModalFirewall, setScriptModalFirewall] = useState<PreviewFirewall | null>(null);

  useEffect(() => {
    loadPreviewData();
  }, [orderId]);

  const loadPreviewData = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/workorders/${orderId}/preview`);
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
      toast.apiError(error, '加载预览数据失败');
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
                <UnmatchedPoliciesTable policies={previewData.unmatched_policies} />
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
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setScriptModalFirewall(group.firewall)}
                  title="查看要推送到此防火墙的 CLI 命令脚本（不连设备）"
                >
                  <FileCode className="h-4 w-4 mr-1" />
                  查看脚本
                </Button>
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

            {/* 策略表格 (原始 + SNAT/PASS_THROUGH + warnings) */}
            <FirewallPolicyTable group={group} />
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

      {/* 推送脚本弹窗（dry-run） */}
      {scriptModalFirewall && (
        <PushScriptModal
          orderId={Number(orderId)}
          firewall={scriptModalFirewall}
          onClose={() => setScriptModalFirewall(null)}
        />
      )}
    </div>
  );
};
