import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, AlertTriangle, ChevronDown, ChevronRight, Send, Loader2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { UnmatchedPoliciesTable } from '../components/preview/UnmatchedPoliciesTable';
import { FirewallPolicyTable } from '../components/preview/FirewallPolicyTable';
import { Badge } from '../components/ui/Badge';
import { togglePlanRowIgnore, commitOrder } from '../lib/api';
import { toast } from '../lib/toast';
import type {
  FirewallGroup,
  PreviewData,
} from '../types';

// ============================================================
// Execution Plan 架构 (2026-06-28)
// ============================================================
//
// 本页是"渲染器 + 开关触发器":
//   - 状态: planData (后端 GET /preview 返回的 plan_data, 含 row_uuid + is_ignored)
//   - 交互: 删除/恢复 (PUT /plan/ignore, 乐观更新 — 零延迟 UI)
//   - 提交: 点击"下一步: 提交并推送" → POST /commit (把快照写入物理表) → 跳 /push
//
// 已移除的旧特性:
//   - 自动执行复选框 (现在所有策略统一走 V2 推送管线, 单墙粒度在 Push 页选)
//   - 查看脚本按钮 (改用提交 → Push 页推送, 不再有 dry-run modal)
//
// 注: types/preview.ts 里 PreviewPolicy 的 row_uuid / is_ignored 字段由 FirewallPolicyTable 使用

export const Preview = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [planData, setPlanData] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  // 提交中标记: 防止重复点击 /commit (后端有唯一性约束但前端先挡)
  const [isCommitting, setIsCommitting] = useState(false);
  // 异常提示折叠状态 (沿用旧行为): 默认折叠, 点击展开
  const [anomaliesExpanded, setAnomaliesExpanded] = useState(false);

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
      setPlanData(data);
    } catch (error) {
      toast.apiError(error, '加载预览数据失败');
    } finally {
      setLoading(false);
    }
  };

  // ============================================================
  // 切换单行 is_ignored (软删除/恢复) — 乐观更新
  // ============================================================
  //
  // 设计: 用户点击"删除/恢复" → 立刻更新本地 state (UI 瞬间响应) →
  //       异步发 PUT /plan/ignore → 失败回滚 + 重拉数据
  //
  // 这是"乐观更新 (Optimistic UI)"模式: 不等网络, 先更新内存里的 planData
  const handleToggleIgnore = async (rowUuid: string, currentIgnoreStatus: boolean) => {
    if (!orderId || !planData) return;
    const newIgnoreStatus = !currentIgnoreStatus;

    // 1. 乐观更新: 立刻翻转内存里的 is_ignored, UI 零延迟
    setPlanData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        firewall_groups: prev.firewall_groups.map((group: FirewallGroup) => ({
          ...group,
          policies: group.policies.map((p) =>
            p.row_uuid === rowUuid ? { ...p, is_ignored: newIgnoreStatus } : p,
          ),
        })),
      };
    });

    // 2. 异步发请求给后端同步状态 (悄悄的, 不再 loading)
    try {
      await togglePlanRowIgnore(Number(orderId), rowUuid, newIgnoreStatus);
      // 成功: 什么都不做, UI 已经提前更新
    } catch (error) {
      // 3. 失败: 回滚 + 提示 + 重新拉数据 (极端情况: 本地状态可能错乱, 用 server truth 覆盖)
      toast.apiError(error, newIgnoreStatus ? '删除失败,已回滚' : '恢复失败,已回滚');
      await loadPreviewData();
    }
  };

  // ============================================================
  // "下一步" = 自动提交 + 跳转
  // ============================================================
  //
  // 用户说"提交(下一步时自动提交)": 点击后:
  //   1. POST /commit — 把 Execution Plan 快照写入物理 policies 表
  //      (后端根据 is_ignored 标记 push_status: true→'ignored', false→'pending')
  //   2. 成功 → 跳转到 /push 页 (沿用旧的 V2 推送管线)
  //   3. 失败 → toast 提示, 不跳转, 让用户修复
  const handleNext = async () => {
    if (!orderId || !planData || isCommitting) return;

    // 前端校验: 有 unmatched_policies 时阻断 (后端也会挡, 前端先友好提示)
    if (planData.unmatched_policies.length > 0) {
      toast.warning(
        `存在 ${planData.unmatched_policies.length} 条未匹配防火墙的策略,无法提交。请先回编辑页修改源/目的 IP。`,
      );
      return;
    }

    try {
      setIsCommitting(true);
      const result = await commitOrder(Number(orderId));
      toast.success(
        `执行计划已提交 (${result.inserted_count} 条策略入库)`,
      );
      // 提交成功 → 跳推送页
      navigate(`/order/${orderId}/push`);
    } catch (error) {
      toast.apiError(error, '提交失败,请重试');
    } finally {
      setIsCommitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-lg">加载中...</div>
      </div>
    );
  }

  if (!planData) {
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
            title="返回编辑原始表格 (会作废当前执行计划快照,下次进入预览页会自动重算)"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">策略预览</h1>
            <p className="text-muted-foreground mt-1">
              {planData.order.title} · 工单号: {planData.order.order_no}
            </p>
          </div>
        </div>
        <Button
          onClick={handleNext}
          size="lg"
          disabled={isCommitting}
        >
          {isCommitting ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              提交中...
            </>
          ) : (
            <>
              <Send className="h-4 w-4 mr-2" />
              下一步：提交并推送
            </>
          )}
        </Button>
      </div>

      {/* 警告和错误提示 (沿用旧行为: 默认折叠, 点击展开, 头部显示计数徽章) */}
      {(planData.warnings.length > 0 || planData.errors.length > 0 || planData.unmatched_policies.length > 0) && (
        <Card className="border-yellow-500 bg-yellow-50">
          <CardHeader
            className="cursor-pointer select-none hover:bg-yellow-100 transition-colors"
            onClick={() => setAnomaliesExpanded(!anomaliesExpanded)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {anomaliesExpanded ? (
                  <ChevronDown className="h-4 w-4 text-yellow-700" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-yellow-700" />
                )}
                <AlertTriangle className="h-5 w-5 text-yellow-600" />
                <CardTitle className="text-yellow-800">异常提示</CardTitle>
                {/* 计数徽章: 默认折叠时一眼看到数量 */}
                <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-200 text-yellow-800">
                  {planData.errors.length + planData.warnings.length + planData.unmatched_policies.length} 条
                </span>
              </div>
              <span className="text-xs text-yellow-600">
                {anomaliesExpanded ? '点击折叠' : '点击展开'}
              </span>
            </div>
          </CardHeader>
          {anomaliesExpanded && (
          <CardContent className="space-y-2">
            {planData.errors.length > 0 && (
              <div>
                <div className="font-semibold text-red-600 mb-1">错误：</div>
                <ul className="list-disc list-inside space-y-1">
                  {planData.errors.map((error, idx) => (
                    <li key={idx} className="text-sm text-red-600">{error}</li>
                  ))}
                </ul>
              </div>
            )}
            {planData.warnings.length > 0 && (
              <div>
                <div className="font-semibold text-yellow-700 mb-1">警告：</div>
                <ul className="list-disc list-inside space-y-1">
                  {planData.warnings.map((warning, idx) => (
                    <li key={idx} className="text-sm text-yellow-700">{warning}</li>
                  ))}
                </ul>
              </div>
            )}
            {planData.unmatched_policies.length > 0 && (
              <div>
                <div className="font-semibold text-orange-600 mb-1">
                  未匹配防火墙的策略（{planData.unmatched_policies.length} 条）：
                </div>
                <UnmatchedPoliciesTable policies={planData.unmatched_policies} />
              </div>
            )}
          </CardContent>
          )}
        </Card>
      )}

      {/* 防火墙分组展示 */}
      {planData.firewall_groups.map((group) => (
        <Card key={group.firewall.id}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-xl">
                  {group.firewall.name}
                  {group.firewall.alias && (
                    <span className="text-sm text-muted-foreground ml-2">({group.firewall.alias})</span>
                  )}
                  {/* 边界墙标识 (is_zone_boundary=1) - 只在这台墙上推策略 */}
                  {group.firewall.is_zone_boundary === 1 && (
                    <Badge
                      className="ml-3 bg-emerald-500 hover:bg-emerald-600 text-white"
                      data-testid={`boundary-badge-${group.firewall.id}`}
                      title="该防火墙是区域边界防火墙, 实际推送策略会落到此墙"
                    >
                      <Send className="h-3 w-3 mr-1" />
                      将在此墙推送
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription className="mt-1">
                  类型: {group.firewall.type} | 管理IP: {group.firewall.management_ip} |
                  区域: {group.firewall.belong_region || '未设置'}
                </CardDescription>
              </div>
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                {/* 2026-06-28 移除: 自动执行复选框 (V2 推送管线统一处理, Push 页选单墙粒度) */}
                {/* 2026-06-28 移除: 查看脚本按钮 (改用 提交 → Push 页推送) */}
                <span>
                  共 {group.policies.length} 条策略
                  {group.policies.filter((p) => p.is_ignored).length > 0 && (
                    <span className="ml-2 text-gray-400">
                      (已忽略 {group.policies.filter((p) => p.is_ignored).length})
                    </span>
                  )}
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {/* 策略表格 (直接渲染 plan_data, 不比对原始表格) */}
            <FirewallPolicyTable group={group} onToggleIgnore={handleToggleIgnore} />
          </CardContent>
        </Card>
      ))}

      {/* 底部操作按钮 */}
      <div className="flex justify-end gap-4">
        <Button
          variant="outline"
          onClick={() => navigate(`/order/${orderId}/edit`)}
          disabled={isCommitting}
        >
          返回编辑
        </Button>
        <Button onClick={handleNext} size="lg" disabled={isCommitting}>
          {isCommitting ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              提交中...
            </>
          ) : (
            <>
              <Send className="h-4 w-4 mr-2" />
              下一步：提交并推送
            </>
          )}
        </Button>
      </div>
    </div>
  );
};
