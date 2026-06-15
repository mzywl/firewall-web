import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Hash, ChevronDown, ChevronRight, Server } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { PushLogViewer } from '../components/push/PushLogViewer';
import { useSnapshot, useSnapshotItems, useSnapshotLogs } from '../hooks/useApi';

export const SnapshotDetail = () => {
  const { snapshotId } = useParams<{ snapshotId: string }>();
  const sid = Number(snapshotId);
  const navigate = useNavigate();

  const { data: snapshot, isLoading, refetch: refetchSnap } = useSnapshot(sid);
  const { data: itemsData, refetch: refetchItems } = useSnapshotItems(sid);
  const { data: logsData } = useSnapshotLogs(sid, true, 2000);
  const [expandedItem, setExpandedItem] = useState<number | null>(null);

  const handleRefresh = () => {
    refetchSnap();
    refetchItems();
  };

  if (isLoading) {
    return <div className="p-8 text-center text-muted-foreground">加载中...</div>;
  }
  if (!snapshot) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        快照不存在
        <div className="mt-4">
          <Button onClick={() => navigate('/')}>返回首页</Button>
        </div>
      </div>
    );
  }

  const items = itemsData?.items ?? [];
  const total = itemsData?.total ?? 0;
  const logs = logsData?.logs ?? [];

  const statusColor = (s: string) => {
    switch (s) {
      case 'success':
        return 'bg-green-500/10 text-green-600 border-green-500/30';
      case 'partial':
        return 'bg-yellow-500/10 text-yellow-600 border-yellow-500/30';
      case 'failed':
        return 'bg-red-500/10 text-red-600 border-red-500/30';
      case 'running':
        return 'bg-blue-500/10 text-blue-600 border-blue-500/30';
      default:
        return 'bg-muted text-muted-foreground';
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              推送快照 #{snapshot.id}
              <Badge className={`${statusColor(snapshot.status)} border`}>{snapshot.status}</Badge>
            </h1>
            <p className="text-muted-foreground mt-1 flex items-center gap-2">
              <Hash className="h-3 w-3" />
              batch: <span className="font-mono">{snapshot.batch_id}</span>
              {' · '}
              <Server className="h-3 w-3" />
              防火墙: {snapshot.firewall_id}
              {' · '}
              模式: {snapshot.push_mode}
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={handleRefresh}>
          <RefreshCw className="mr-2 h-4 w-4" />
          刷新
        </Button>
      </div>

      {/* 概览卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold">{snapshot.total_policies}</div>
            <div className="text-xs text-muted-foreground mt-1">总策略</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold text-green-600">{snapshot.new_policies}</div>
            <div className="text-xs text-muted-foreground mt-1">新建</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold text-blue-600">{snapshot.reused_policies}</div>
            <div className="text-xs text-muted-foreground mt-1">复用整条</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold text-purple-600">{snapshot.appended_policies}</div>
            <div className="text-xs text-muted-foreground mt-1">追加</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold text-red-600">{snapshot.failed_policies}</div>
            <div className="text-xs text-muted-foreground mt-1">失败</div>
          </CardContent>
        </Card>
      </div>

      {/* 设备侧快照信息 */}
      <Card>
        <CardHeader>
          <CardTitle>设备侧快照</CardTitle>
          <CardDescription>
            推送前从防火墙拉取的配置快照（用于可追溯 + 后续查重）
          </CardDescription>
        </CardHeader>
        <CardContent>
          {snapshot.has_fetched_snapshot ? (
            <div className="text-sm text-muted-foreground">
              ✓ 已拉取设备侧配置（地址对象 + 策略）。可追溯到推送前设备状态。
            </div>
          ) : (
            <div className="text-sm text-yellow-600">⚠ 设备侧快照未拉取（推送未走到 fetch 阶段）</div>
          )}
        </CardContent>
      </Card>

      {/* 错误日志（如果有） */}
      {snapshot.error_log && (
        <Card className="border-red-500/50">
          <CardHeader>
            <CardTitle className="text-red-600">错误日志</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="bg-red-500/5 p-4 rounded text-xs font-mono whitespace-pre-wrap overflow-x-auto">
              {snapshot.error_log}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* 快照明细 */}
      <Card>
        <CardHeader>
          <CardTitle>策略明细</CardTitle>
          <CardDescription>
            共 {total} 条（每条显示匹配键 + 设备对象 + 原始命令预览；点击展开看完整命令）
          </CardDescription>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">暂无明细</div>
          ) : (
            <div className="space-y-1">
              {items.map((item) => {
                const expanded = expandedItem === item.id;
                return (
                  <div
                    key={item.id}
                    className="border rounded-lg overflow-hidden hover:bg-accent/30 transition-colors"
                  >
                    <button
                      onClick={() => setExpandedItem(expanded ? null : item.id!)}
                      className="w-full p-3 flex items-center justify-between text-left"
                    >
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        {expanded ? (
                          <ChevronDown className="h-4 w-4 flex-shrink-0" />
                        ) : (
                          <ChevronRight className="h-4 w-4 flex-shrink-0" />
                        )}
                        <span className="text-xs text-muted-foreground font-mono w-12 flex-shrink-0">
                          P{item.policy_id}
                        </span>
                        <Badge
                          className={`${statusColor(item.action)} border`}
                          variant="outline"
                        >
                          {item.action}
                        </Badge>
                        <span className="text-sm truncate">
                          {item.match_key ? item.match_key.slice(0, 16) : '-'}
                        </span>
                        {item.device_policy_name && (
                          <span className="text-xs text-muted-foreground truncate">
                            设备: {item.device_policy_name}
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground flex-shrink-0">
                        {item.error_msg ? '✗' : '✓'}
                      </span>
                    </button>
                    {expanded && (
                      <div className="px-4 pb-3 pt-1 space-y-2 text-xs bg-muted/30">
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <span className="text-muted-foreground">源:</span>{' '}
                            <span className="font-mono">
                              {item.device_src_obj || item.src_addr_key?.slice(0, 80)}
                            </span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">目的:</span>{' '}
                            <span className="font-mono">
                              {item.device_dst_obj || item.dst_addr_key?.slice(0, 80)}
                            </span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">服务:</span>{' '}
                            <span className="font-mono">{item.device_service_obj || '-'}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">时间:</span>{' '}
                            <span className="font-mono">{item.device_schedule_obj || '-'}</span>
                          </div>
                        </div>
                        {item.error_msg && (
                          <div className="text-red-600 font-mono">{item.error_msg}</div>
                        )}
                        <details>
                          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                            原始命令
                          </summary>
                          <pre className="mt-2 p-2 bg-background rounded text-xs font-mono whitespace-pre-wrap overflow-x-auto">
                            {item.raw_commands_preview}
                          </pre>
                        </details>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 实时日志 */}
      <PushLogViewer logs={logs} emptyText="暂无实时日志（推送可能未启动或已结束）" />
    </div>
  );
};
