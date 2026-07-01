import { useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Eye } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { SyncScrollTable, type SyncScrollTableRef } from '../components/table/SyncScrollTable';
import { useOrder, usePolicies, useUpdatePolicies } from '../hooks/useOrders';
import type { Policy } from '../types';
import { toast } from '../lib/toast';

export const Edit = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [autoExecute, setAutoExecute] = useState(false);

  // (2026-06-28) imperative ref — handleNext 时从这里拿当前编辑过的数据
  // 不用 usePolicies 返回的 formattedV2Policies (那是陈旧的初次 fetch 快照)
  const editableTableRef = useRef<SyncScrollTableRef>(null);

  const { data: order, isLoading: orderLoading, error: orderError, refetch: refetchOrder } = useOrder(Number(orderId));

  // 获取第一次格式化数据（版本数据，只读）
  const { data: formattedV1Policies, isLoading: v1Loading } = usePolicies(
    Number(orderId),
    'formatted_v1'
  );

  // 获取第二次格式化数据（Policy 表数据，可编辑，有真实ID）
  const { data: formattedV2Policies, isLoading: v2Loading, refetch } = usePolicies(
    Number(orderId),
    'formatted_v2'  // 不传 version，获取 Policy 表数据
  );
  
  const updateMutation = useUpdatePolicies(Number(orderId));

  const handleSave = async (updatedPolicies: Policy[]) => {
    try {
      await updateMutation.mutateAsync(updatedPolicies);
      toast.success('保存成功');
      refetch();

      // 如果勾选了自动执行，直接跳转到推送页面
      if (autoExecute) {
        navigate(`/order/${orderId}/push`);
      }
    } catch (error) {
      toast.apiError(error, '保存失败，请重试');
    }
  };

  const handleNext = async () => {
    // 保存当前编辑 — 优先从 SyncScrollTable 拿实时编辑数据 (2026-06-28 fix)
    // 修复 "Edit 点下一步时, 修改没有保存" bug
    // 原因: 之前用的是 usePolicies 返回的 formattedV2Policies (陈旧的初次 fetch 快照)
    //       同步滚动表格内部 editedPolicies state 才是用户当前编辑的真实数据
    const currentData = editableTableRef.current?.getCurrentData() ?? formattedV2Policies;
    if (currentData && currentData.length > 0) {
      await handleSave(currentData);
    } else if (formattedV2Policies) {
      // 兜底: ref 没拿到数据时用 hook 数据 (理论上不会发生)
      await handleSave(formattedV2Policies);
    }

    // 如果勾选了自动执行，跳转到推送页面
    if (autoExecute) {
      navigate(`/order/${orderId}/push`);
    } else {
      navigate(`/order/${orderId}/preview`);
    }
  };

  const handlePreview = () => {
    navigate(`/order/${orderId}/preview`);
  };

  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'success'> = {
      pending: 'secondary',
      processing: 'default',
      completed: 'success',
      failed: 'destructive',
    };
    const labels: Record<string, string> = {
      pending: '待处理',
      processing: '处理中',
      completed: '已完成',
      failed: '失败',
    };
    return <Badge variant={variants[status] || 'default'}>{labels[status] || status}</Badge>;
  };

  if (orderLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (orderError) {
    return (
      <div className="text-center py-12">
        <p className="text-red-600">加载工单失败</p>
        <Button className="mt-4" onClick={() => refetchOrder()}>
          重试
        </Button>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">工单不存在</p>
        <Button className="mt-4" onClick={() => navigate('/')}>
          返回首页
        </Button>
      </div>
    );
  }

  // 判断是否使用虚拟滚动（行数 > 100）
  const useVirtualScroll = (formattedV2Policies?.length || 0) > 100;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate('/')}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">{order.title}</h1>
            <div className="text-muted-foreground mt-1 flex items-center gap-2">
              <span>工单号: {order.order_no}</span>
              <span>·</span>
              {getStatusBadge(order.status)}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handlePreview}
          >
            <Eye className="mr-2 h-4 w-4" />
            预览
          </Button>
          <Button
            onClick={handleNext}
            disabled={updateMutation.isPending}
          >
            <Save className="mr-2 h-4 w-4" />
            {autoExecute ? '保存并推送' : '下一步'}
          </Button>
        </div>
      </div>

      {/* 工单信息 */}
      <Card>
        <CardHeader>
          <CardTitle>工单信息</CardTitle>
          <CardDescription>{order.description}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">创建人：</span>
              <span className="font-medium ml-2">{order.created_by || '-'}</span>
            </div>
            <div>
              <span className="text-muted-foreground">创建时间：</span>
              <span className="font-medium ml-2">
                {new Date(order.created_at).toLocaleString('zh-CN')}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">更新时间：</span>
              <span className="font-medium ml-2">
                {new Date(order.updated_at).toLocaleString('zh-CN')}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">策略数量：</span>
              <span className="font-medium ml-2">{formattedV2Policies?.length || 0}</span>
            </div>
          </div>
          
          {/* 自动执行选项 */}
          <div className="mt-4 pt-4 border-t">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={autoExecute}
                onChange={(e) => setAutoExecute(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
              />
              <span className="text-sm font-medium">
                自动执行（保存后直接跳转到推送页面，跳过预览步骤）
              </span>
            </label>
          </div>
        </CardContent>
      </Card>

      {/* 双表格显示（同步滚动） */}
      {!useVirtualScroll && (
        <Card>
          <CardHeader>
            <CardTitle>表格编辑（双表格同步滚动）</CardTitle>
            <CardDescription>
              上方为第一次格式化结果（只读），下方为第二次格式化结果（可编辑）。
              支持点击编辑、Tab 切换、Enter 换行、Ctrl+C/V 复制粘贴。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SyncScrollTable
              ref={editableTableRef}
              topPolicies={formattedV1Policies || []}
              bottomPolicies={formattedV2Policies || []}
              onUpdate={handleSave}
              loading={v1Loading || v2Loading}
            />
          </CardContent>
        </Card>
      )}

      {/* 虚拟滚动表格（行数 > 100） */}
      {useVirtualScroll && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>第一次格式化（只读）</CardTitle>
              <CardDescription>标准化字段名 + 格式化IP/端口</CardDescription>
            </CardHeader>
          <CardContent>
            <SyncScrollTable
              mode="single"
              policies={formattedV1Policies || []}
              editable={false}
              loading={v1Loading}
            />
          </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>第二次格式化（可编辑）</CardTitle>
              <CardDescription>删除示例策略 - 使用虚拟滚动优化性能</CardDescription>
            </CardHeader>
          <CardContent>
            <SyncScrollTable
              ref={editableTableRef}
              mode="single"
              policies={formattedV2Policies || []}
              editable={true}
              onUpdate={handleSave}
              loading={v2Loading || updateMutation.isPending}
            />
          </CardContent>
          </Card>
        </>
      )}
    </div>
  );
};
