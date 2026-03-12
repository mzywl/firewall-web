import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, GitCompare } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { PolicyTable } from '../components/table/PolicyTable';
import { useOrder, usePolicies, useVersions } from '../hooks/useApi';

export const Preview = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [leftVersion, setLeftVersion] = useState<'original' | 'formatted_v1' | 'formatted_v2' | 'user_modified'>('original');
  const [rightVersion, setRightVersion] = useState<'original' | 'formatted_v1' | 'formatted_v2' | 'user_modified'>('formatted_v1');

  const { data: order } = useOrder(Number(orderId));
  const { data: versions } = useVersions(Number(orderId));
  const { data: leftPolicies, isLoading: leftLoading } = usePolicies(Number(orderId), leftVersion);
  const { data: rightPolicies, isLoading: rightLoading } = usePolicies(Number(orderId), rightVersion);

  const versionLabels: Record<string, string> = {
    original: '原始版本',
    formatted_v1: '第一次格式化',
    formatted_v2: '第二次格式化',
    user_modified: '用户编辑版本',
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
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
              {order?.title} · 工单号: {order?.order_no}
            </p>
          </div>
        </div>
        <Button onClick={() => navigate(`/order/${orderId}/push`)}>
          开始推送
        </Button>
      </div>

      {/* 版本信息 */}
      {versions && versions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>版本历史</CardTitle>
            <CardDescription>查看不同版本的策略数据</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-4">
              {versions.map((version) => (
                <div
                  key={version.id}
                  className="flex-1 p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <div className="font-medium">{versionLabels[version.version_type]}</div>
                  <div className="text-sm text-muted-foreground mt-1">
                    {version.policy_count} 条策略
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {new Date(version.created_at).toLocaleString('zh-CN')}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 对比视图 */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <GitCompare className="h-5 w-5" />
            <CardTitle>版本对比</CardTitle>
          </div>
          <CardDescription>选择两个版本进行对比</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid md:grid-cols-2 gap-6">
            {/* 左侧版本 */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">左侧版本</h3>
                <select
                  value={leftVersion}
                  onChange={(e) => setLeftVersion(e.target.value as any)}
                  className="px-3 py-1 border rounded-md text-sm bg-background"
                >
                  <option value="original">原始版本</option>
                  <option value="formatted">格式化版本</option>
                  <option value="user_modified">用户编辑版本</option>
                </select>
              </div>
              <div className="border rounded-lg overflow-hidden">
                <PolicyTable
                  policies={leftPolicies || []}
                  loading={leftLoading}
                  editable={false}
                />
              </div>
              <div className="text-sm text-muted-foreground text-center">
                共 {leftPolicies?.length || 0} 条策略
              </div>
            </div>

            {/* 右侧版本 */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">右侧版本</h3>
                <select
                  value={rightVersion}
                  onChange={(e) => setRightVersion(e.target.value as any)}
                  className="px-3 py-1 border rounded-md text-sm bg-background"
                >
                  <option value="original">原始版本</option>
                  <option value="formatted">格式化版本</option>
                  <option value="user_modified">用户编辑版本</option>
                </select>
              </div>
              <div className="border rounded-lg overflow-hidden">
                <PolicyTable
                  policies={rightPolicies || []}
                  loading={rightLoading}
                  editable={false}
                />
              </div>
              <div className="text-sm text-muted-foreground text-center">
                共 {rightPolicies?.length || 0} 条策略
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
