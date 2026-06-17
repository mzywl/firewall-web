import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Play,
  RotateCcw,
  CheckCircle,
  Wifi,
  Server,
  Hash,
  XCircle,
  ExternalLink,
  AlertCircle,
} from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { PushProgressBar } from '../components/push/PushProgressBar';
import { PushLogViewer } from '../components/push/PushLogViewer';
import {
  useOrder,
  useStartPushV2,
  useFirewalls,
  useTestConnection,
  useSnapshot,
  useSnapshotLogs,
  usePolicies,
} from '../hooks/useApi';
import type { PushMode, PushLogsResponse } from '../lib/api';
import { toast } from '../lib/toast';

export const Push = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();

  const [firewallId, setFirewallId] = useState<number | null>(null);
  const [mode, setMode] = useState<PushMode>('deduplicate');
  const [snapshotId, setSnapshotId] = useState<number | null>(null);
  const [isPushing, setIsPushing] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);

  const { data: order } = useOrder(Number(orderId));
  const { data: policies } = usePolicies(Number(orderId), 'user_modified');
  const { data: firewalls, isLoading: loadingFws } = useFirewalls();
  const startPushMutation = useStartPushV2(Number(orderId));
  const testConnMutation = useTestConnection();
  const { data: snapshot } = useSnapshot(snapshotId);
  const { data: logsData } = useSnapshotLogs(snapshotId, isPushing || isCompleted, 1500);

  // 默认选第一个防火墙
  useEffect(() => {
    if (!firewallId && firewalls && firewalls.length > 0) {
      setFirewallId(firewalls[0].id);
    }
  }, [firewalls, firewallId]);

  // snapshot 进入 success/failed/partial 状态 → 推送结束
  useEffect(() => {
    if (snapshot && (snapshot.status === 'success' || snapshot.status === 'failed' || snapshot.status === 'partial')) {
      setIsPushing(false);
      setIsCompleted(true);
    }
  }, [snapshot]);

  const selectedFw = firewalls?.find((f) => f.id === firewallId);

  const handleStart = async () => {
    if (!firewallId) {
      toast.warning('请先选择目标防火墙');
      return;
    }
    if (!policies || policies.length === 0) {
      toast.warning('工单没有可推送的策略');
      return;
    }
    setIsCompleted(false);
    setIsPushing(true);
    setTestResult(null);
    setSnapshotId(null);
    try {
      const result = await startPushMutation.mutateAsync({ firewallId, mode });
      if (result.snapshot_id) {
        setSnapshotId(result.snapshot_id);
      }
    } catch (error) {
      setIsPushing(false);
      setIsCompleted(false);
      toast.apiError(error, '启动推送失败');
    }
  };

  const handleReset = () => {
    setIsPushing(false);
    setIsCompleted(false);
    setSnapshotId(null);
    setTestResult(null);
  };

  const handleTestConnection = async () => {
    if (!firewallId) {
      toast.warning('请先选择目标防火墙');
      return;
    }
    setTestResult(null);
    try {
      const r = await testConnMutation.mutateAsync(firewallId);
      setTestResult({
        ok: r.success,
        message: r.success
          ? `✓ 连接成功 (${r.elapsed_ms}ms)\n设备类型: ${r.device_type}\n版本: ${r.version.slice(0, 100)}`
          : `✗ 连接失败: ${r.error}`,
      });
    } catch (error: any) {
      setTestResult({
        ok: false,
        message: `✗ 测试失败: ${error?.response?.data?.detail || error?.message}`,
      });
    }
  };

  // 进度（用 snapshot 统计 + 实时日志数量估算）
  const total = snapshot?.total_policies ?? policies?.length ?? 0;
  const success = snapshot?.new_policies ?? 0;
  const failed = snapshot?.failed_policies ?? 0;
  const reused = snapshot?.reused_policies ?? 0;
  const appended = snapshot?.appended_policies ?? 0;
  const pending = Math.max(0, total - success - failed);
  const progress = total > 0 ? Math.round(((success + failed) / total) * 100) : 0;

  // 日志
  const logs = (logsData as PushLogsResponse | undefined)?.logs ?? [];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate(`/order/${orderId}/edit`)}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">策略推送（v2 流水线）</h1>
            <p className="text-muted-foreground mt-1">
              {order?.title} · 工单号: {order?.order_no}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          {!isPushing && !isCompleted && (
            <Button onClick={handleStart} disabled={!firewallId || startPushMutation.isPending}>
              <Play className="mr-2 h-4 w-4" />
              {startPushMutation.isPending ? '启动中...' : '开始推送'}
            </Button>
          )}
          {isCompleted && (
            <>
              <Button variant="outline" onClick={handleReset}>
                <RotateCcw className="mr-2 h-4 w-4" />
                重新推送
              </Button>
              {snapshotId && (
                <Button variant="outline" onClick={() => navigate(`/snapshot/${snapshotId}`)}>
                  <ExternalLink className="mr-2 h-4 w-4" />
                  查看快照 #{snapshotId}
                </Button>
              )}
              <Button onClick={() => navigate(`/order/${orderId}/edit`)}>
                <CheckCircle className="mr-2 h-4 w-4" />
                返回编辑
              </Button>
            </>
          )}
        </div>
      </div>

      {/* 配置区：防火墙 + 模式 + 测连通 */}
      {!isPushing && !isCompleted && (
        <Card>
          <CardHeader>
            <CardTitle>推送配置</CardTitle>
            <CardDescription>选择目标防火墙和推送模式，建议先测连通</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 防火墙选择 */}
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <Server className="h-4 w-4" />
                  目标防火墙
                </label>
                <select
                  className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
                  value={firewallId ?? ''}
                  onChange={(e) => {
                    setFirewallId(Number(e.target.value));
                    setTestResult(null);
                  }}
                  disabled={loadingFws}
                >
                  {loadingFws ? (
                    <option>加载中...</option>
                  ) : firewalls && firewalls.length > 0 ? (
                    firewalls.map((fw) => (
                      <option key={fw.id} value={fw.id}>
                        {fw.name} ({fw.management_ip}) {fw.region ? `· ${fw.region}` : ''}
                      </option>
                    ))
                  ) : (
                    <option>暂无可用防火墙</option>
                  )}
                </select>
                {selectedFw && (
                  <div className="text-xs text-muted-foreground">
                    类型: <span className="font-mono">{selectedFw.type}</span> · 状态:{' '}
                    <span className={selectedFw.is_active ? 'text-green-600' : 'text-red-600'}>
                      {selectedFw.is_active ? '启用' : '停用'}
                    </span>
                  </div>
                )}
              </div>

              {/* 推送模式 */}
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <Hash className="h-4 w-4" />
                  推送模式
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setMode('deduplicate')}
                    className={`p-3 rounded-md border text-left text-sm transition-colors ${
                      mode === 'deduplicate'
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-input hover:bg-accent'
                    }`}
                  >
                    <div className="font-medium">查重模式</div>
                    <div className="text-xs text-muted-foreground mt-1">
                      复用整条已存在策略，对象不重用才新建
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode('force_push')}
                    className={`p-3 rounded-md border text-left text-sm transition-colors ${
                      mode === 'force_push'
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'border-input hover:bg-accent'
                    }`}
                  >
                    <div className="font-medium">全推模式</div>
                    <div className="text-xs text-muted-foreground mt-1">
                      对象复用，整条策略必新建（强制落盘）
                    </div>
                  </button>
                </div>
              </div>
            </div>

            {/* 测连通 */}
            <div className="flex items-center gap-2 pt-2 border-t">
              <Button
                variant="outline"
                size="sm"
                onClick={handleTestConnection}
                disabled={!firewallId || testConnMutation.isPending}
              >
                <Wifi className="mr-2 h-4 w-4" />
                {testConnMutation.isPending ? '测试中...' : '测连通'}
              </Button>
              {testResult && (
                <div
                  className={`flex items-start gap-2 text-sm flex-1 ${
                    testResult.ok ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {testResult.ok ? (
                    <CheckCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  ) : (
                    <XCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  )}
                  <pre className="whitespace-pre-wrap text-xs font-mono">{testResult.message}</pre>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 进度 + 日志 */}
      {(isPushing || isCompleted) && (
        <>
          <PushProgressBar
            total={total}
            success={success}
            failed={failed}
            pending={pending}
            progress={progress}
            isProcessing={isPushing}
          />

          {snapshot && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">快照统计</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-5 gap-4 text-center text-sm">
                  <div>
                    <div className="text-2xl font-bold">{total}</div>
                    <div className="text-xs text-muted-foreground">总策略</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-green-600">{success}</div>
                    <div className="text-xs text-muted-foreground">新建</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-blue-600">{reused}</div>
                    <div className="text-xs text-muted-foreground">复用整条</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-purple-600">{appended}</div>
                    <div className="text-xs text-muted-foreground">追加</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-red-600">{failed}</div>
                    <div className="text-xs text-muted-foreground">失败</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <PushLogViewer logs={logs} />
        </>
      )}

      {/* 完成提示 */}
      {isCompleted && snapshot && (
        <Card
          className={
            snapshot.status === 'success'
              ? 'border-green-500/50 bg-green-500/5'
              : snapshot.status === 'partial'
              ? 'border-yellow-500/50 bg-yellow-500/5'
              : 'border-red-500/50 bg-red-500/5'
          }
        >
          <CardHeader>
            <div className="flex items-center gap-2">
              {snapshot.status === 'success' ? (
                <CheckCircle className="h-5 w-5 text-green-500" />
              ) : (
                <AlertCircle className="h-5 w-5 text-red-500" />
              )}
              <CardTitle>
                推送{snapshot.status === 'success' ? '成功' : snapshot.status === 'partial' ? '部分成功' : '失败'}
              </CardTitle>
            </div>
            <CardDescription>
              耗时 {snapshot.finished_at && snapshot.started_at
                ? `${Math.round((new Date(snapshot.finished_at).getTime() - new Date(snapshot.started_at).getTime()) / 1000)}s`
                : '-'}
              {' '}· 快照 #{snapshot.id} (batch {snapshot.batch_id.slice(0, 8)})
            </CardDescription>
          </CardHeader>
        </Card>
      )}
    </div>
  );
};
