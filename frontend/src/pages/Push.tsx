/**
 * Push 页面 (C7 redesign)
 *
 * 数据流:
 *   1. 拉 /api/workorders/{orderId}/preview → firewall_groups
 *   2. 按 firewall_groups 顺序渲染, 每面墙 1 个 Card
 *   3. 每面墙 Card 折叠区: 调 generate-script 拉该墙命令预览 (按需, 默认折叠)
 *   4. 每面墙独立 "推送到这面墙" 按钮 + 进度 + 实时日志
 *
 * 关键改动 vs 旧版 (C6 之前的 Push.tsx):
 *   - 不再用 useFirewalls() 拿所有墙, 改用 preview.firewall_groups (前面过滤出来的墙)
 *   - 每面墙独立推送, 3 模式 Radio 全局共享 (顶部 1 份)
 *   - 不管哪个模式, 都展示 generate-script 命令预览 (按需 fetch)
 */
import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Play,
  CheckCircle,
  XCircle,
  Server,
  Hash,
  FileCode,
  Copy,
  Check,
  AlertCircle,
  AlertTriangle,
  Send,
  Loader2,
  RotateCw,
  RotateCcw,
  Sparkles,
  X,
} from 'lucide-react';
import { Button } from '../components/ui/Button';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { PushProgressBar } from '../components/push/PushProgressBar';
import { PushLogViewer } from '../components/push/PushLogViewer';
import {
  PolicyMatchBadge,
  type MatchMode,
} from '../components/push/PolicyMatchBadge';
import {
  useStartPushV2,
  useSnapshot,
  useSnapshotLogs,
} from '../hooks/usePush';
import { getPushTasks, type PushMode, type PushLogsResponse } from '../lib/api';
import { toast } from '../lib/toast';
import type {
  PreviewData,
  FirewallGroup,
  GenerateScriptResponse,
  GenerateScriptNewPolicy,
} from '../types/preview';

// 复制到剪贴板 (含非安全上下文 fallback)
// 非安全上下文 (HTTP 非 localhost / 内嵌 iframe) 时 navigator.clipboard 是 undefined
// 这种环境下用隐藏 textarea + execCommand('copy') 兼容
async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.top = '0';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {
    const ok = document.execCommand('copy');
    if (!ok) throw new Error('execCommand 复制失败');
  } finally {
    document.body.removeChild(ta);
  }
}

export const Push = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const oid = Number(orderId);

  // 推送模式: defaultMode 是顶部 Radio 设的全局默认,
  // wallModeOverrides 是单墙覆盖 (无 key = 继承默认)
  const [defaultMode, setDefaultMode] = useState<PushMode>('deduplicate');
  const [wallModeOverrides, setWallModeOverrides] = useState<Record<number, PushMode>>({});

  const setWallModeOverride = (fwId: number, mode: PushMode | null) => {
    setWallModeOverrides((prev) => {
      const next = { ...prev };
      if (mode === null) delete next[fwId];
      else next[fwId] = mode;
      return next;
    });
  };

  // 一键 dry-run 全部: 用 token 触发子组件 useEffect, 父组件只看完成数做进度
  const [batchQueryTrigger, setBatchQueryTrigger] = useState(0);
  const [batchQueryProgress, setBatchQueryProgress] = useState<{ done: number; total: number } | null>(null);

  const handleBatchDryRun = () => {
    const total = previewData?.firewall_groups.length ?? 0;
    if (total === 0) {
      toast.warning('没有可查询的防火墙');
      return;
    }
    setBatchQueryProgress({ done: 0, total });
    setBatchQueryTrigger((t) => t + 1);
  };

  const handleCardBatchDone = () => {
    setBatchQueryProgress((prev) => (prev ? { ...prev, done: prev.done + 1 } : prev));
  };

  // batchQueryProgress 完成 → 1.5s 后自动清
  useEffect(() => {
    if (batchQueryProgress && batchQueryProgress.done >= batchQueryProgress.total) {
      const timer = setTimeout(() => setBatchQueryProgress(null), 1500);
      return () => clearTimeout(timer);
    }
  }, [batchQueryProgress]);

  // (2026-06-28) 改为调用 /api/push/orders/<id>/tasks (物理 Policy 表 + pending 过滤)
  // 替换原本的 /api/workorders/<id>/preview (Execution Plan 快照)
  // helper 在 api.ts 里做字段适配, 返回 PreviewData 兼容 shape, 下游代码不变
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(true);

  // 拉 tasks (Push 页进入时)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoadingPreview(true);
        const data = await getPushTasks(oid);
        if (!cancelled) setPreviewData(data);
      } catch (e) {
        if (!cancelled) toast.apiError(e, '加载推送任务失败');
      } finally {
        if (!cancelled) setLoadingPreview(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [oid]);

  // 一键推送所有: 串行执行, 须每面墙都完成过 dry-run 才能开启
  // dryRunCompleted: 跟踪哪些墙已成功加载过 dry-run 数据
  const [dryRunCompleted, setDryRunCompleted] = useState<Set<number>>(new Set());
  // batchPushTrigger: bump 触发新一轮批量推送
  const [batchPushTrigger, setBatchPushTrigger] = useState(0);
  // batchPushIndex: 当前正在推的墙在 firewall_groups 里的索引
  const [batchPushIndex, setBatchPushIndex] = useState(0);
  // batchPushProgress: 推送进度显示
  const [batchPushProgress, setBatchPushProgress] = useState<{
    done: number;
    total: number;
    currentFwName?: string;
  } | null>(null);
  // showBatchPushModal: 自定义 Modal 显隐
  const [showBatchPushModal, setShowBatchPushModal] = useState(false);

  const fwIds: number[] =
    previewData?.firewall_groups.map((g) => g.firewall.id) ?? [];

  const handleCardDryRunLoaded = (fwId: number) => {
    setDryRunCompleted((prev) => {
      if (prev.has(fwId)) return prev;
      const next = new Set(prev);
      next.add(fwId);
      return next;
    });
  };

  const handleCardBatchPushStart = (fwName: string) => {
    setBatchPushProgress((prev) => (prev ? { ...prev, currentFwName: fwName } : prev));
  };

  const handleCardBatchPushDone = () => {
    setBatchPushProgress((prev) =>
      prev ? { ...prev, done: prev.done + 1, currentFwName: undefined } : prev,
    );
    setBatchPushIndex((i) => i + 1);
  };

  const handleOpenBatchPushModal = () => {
    const total = fwIds.length;
    if (total === 0) {
      toast.warning('没有可推送的防火墙');
      return;
    }
    const notReady = fwIds.filter((id) => !dryRunCompleted.has(id));
    if (notReady.length > 0) {
      toast.warning(
        `还有 ${notReady.length} 面墙未完成 dry-run, 请先点击"一键查询所有墙"加载命令`,
      );
      return;
    }
    setShowBatchPushModal(true);
  };

  const handleConfirmBatchPush = () => {
    setShowBatchPushModal(false);
    setBatchPushProgress({ done: 0, total: fwIds.length });
    setBatchPushIndex(0);
    setBatchPushTrigger((t) => t + 1);
  };

  // batchPushProgress 完成 → 1.5s 后自动清
  useEffect(() => {
    if (batchPushProgress && batchPushProgress.done >= batchPushProgress.total) {
      const timer = setTimeout(() => setBatchPushProgress(null), 1500);
      return () => clearTimeout(timer);
    }
  }, [batchPushProgress]);

  if (loadingPreview) {
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
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate(`/order/${oid}/edit`)}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">策略推送</h1>
            <p className="text-muted-foreground mt-1">
              {previewData.order.title} · 工单号: {previewData.order.order_no}
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={() => navigate(`/order/${oid}/edit`)}>
          返回编辑
        </Button>
      </div>

      {/* 顶部全局: 默认推送模式 (单墙可单独覆盖) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Hash className="h-4 w-4" />
            默认推送模式 (所有墙未单独设置时使用)
          </CardTitle>
          <CardDescription>
            单墙可在本墙 Card 顶部单独覆盖该默认; 覆盖后顶部切换不影响已覆盖的墙
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <ModeRadio
              current={defaultMode}
              value="deduplicate"
              title="查重模式"
              desc="复用整条已存在策略，对象不重用才新建"
              onChange={setDefaultMode}
            />
            <ModeRadio
              current={defaultMode}
              value="force_push"
              title="全推模式"
              desc="对象与策略全错开新建（强制落盘）"
              onChange={setDefaultMode}
            />
            <ModeRadio
              current={defaultMode}
              value="reuse_objects"
              title="对象复用模式"
              desc="复用相同 IP/端口组，策略行新建"
              onChange={setDefaultMode}
            />
          </div>
          <div className="mt-3 pt-3 border-t flex items-center gap-3 flex-wrap text-xs">
            <Button
              variant="outline"
              size="sm"
              onClick={handleBatchDryRun}
              disabled={
                !previewData ||
                previewData.firewall_groups.length === 0 ||
                (batchQueryProgress !== null && batchQueryProgress.done < batchQueryProgress.total) ||
                (batchPushProgress !== null && batchPushProgress.done < batchPushProgress.total)
              }
              data-testid="batch-dryrun-all"
              title="对所有墙并发触发 dry-run (不连设备), 串行执行避免 SSH 资源争用"
            >
              <FileCode className="mr-2 h-4 w-4" />
              一键查询所有墙 (dry-run)
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleOpenBatchPushModal}
              disabled={
                !previewData ||
                previewData.firewall_groups.length === 0 ||
                (batchPushProgress !== null && batchPushProgress.done < batchPushProgress.total) ||
                fwIds.some((id) => !dryRunCompleted.has(id))
              }
              data-testid="batch-push-all"
              title={
                fwIds.some((id) => !dryRunCompleted.has(id))
                  ? '必须先对每面墙完成一次 dry-run 才能批量推送'
                  : '对所有墙串行启动推送 (按防火墙_groups 顺序)'
              }
            >
              <Play className="mr-2 h-4 w-4" />
              一键推送所有墙
            </Button>
            {batchQueryProgress && (
              <span className="text-muted-foreground">
                查询进度:{' '}
                <span className="font-mono font-semibold text-slate-700">
                  {batchQueryProgress.done} / {batchQueryProgress.total}
                </span>
              </span>
            )}
            {batchPushProgress && (
              <span className="text-muted-foreground">
                推送进度:{' '}
                <span className="font-mono font-semibold text-slate-700">
                  {batchPushProgress.done} / {batchPushProgress.total}
                </span>
                {batchPushProgress.currentFwName && (
                  <span className="ml-2">· 当前: {batchPushProgress.currentFwName}</span>
                )}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 防火墙分组 (按 preview.firewall_groups 顺序) */}
      {previewData.firewall_groups.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            preview 没找到命中的防火墙, 无需推送
          </CardContent>
        </Card>
      ) : (
        previewData.firewall_groups.map((group) => {
          const fw = group.firewall;
          const effectiveMode = wallModeOverrides[fw.id] ?? defaultMode;
          return (
            <FirewallPushCard
              key={fw.id}
              orderId={oid}
              group={group}
              defaultMode={defaultMode}
              effectiveMode={effectiveMode}
              wallOverride={wallModeOverrides[fw.id] ?? null}
              onSetOverride={(m) => setWallModeOverride(fw.id, m)}
              batchQueryTrigger={batchQueryTrigger}
              onBatchQueryComplete={handleCardBatchDone}
              batchPushTrigger={batchPushTrigger}
              batchPushTargetFwId={
                batchPushProgress !== null && batchPushProgress.done < batchPushProgress.total
                  ? fwIds[batchPushIndex] ?? null
                  : null
              }
              onDryRunLoaded={handleCardDryRunLoaded}
              onBatchPushStart={handleCardBatchPushStart}
              onBatchPushDone={handleCardBatchPushDone}
            />
          );
        })
      )}

      {/* 未匹配的策略 (提示一下, 但不推送) */}
      {previewData.unmatched_policies.length > 0 && (
        <Card className="border-yellow-500/50 bg-yellow-500/5">
          <CardHeader>
            <CardTitle className="text-base text-yellow-700 flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              未匹配防火墙的策略 ({previewData.unmatched_policies.length} 条)
            </CardTitle>
            <CardDescription>
              这部分策略 preview 没找到命中的防火墙, 不会出现在上面的墙列表里
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* 错误提示 */}
      {previewData.errors.length > 0 && (
        <Card className="border-red-500/50">
          <CardHeader>
            <CardTitle className="text-base text-red-600">错误</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc list-inside text-sm text-red-600 space-y-1">
              {previewData.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* 一键推送确认 Modal */}
      {showBatchPushModal && (
        <BatchPushConfirmModal
          previewData={previewData}
          defaultMode={defaultMode}
          wallModeOverrides={wallModeOverrides}
          onConfirm={handleConfirmBatchPush}
          onCancel={() => setShowBatchPushModal(false)}
        />
      )}
    </div>
  );
};

// =============================================================
// ModeRadio - 3 模式单选按钮
// =============================================================

interface ModeRadioProps {
  current: PushMode;
  value: PushMode;
  title: string;
  desc: string;
  onChange: (v: PushMode) => void;
}

const ModeRadio = ({ current, value, title, desc, onChange }: ModeRadioProps) => (
  <button
    type="button"
    onClick={() => onChange(value)}
    className={`p-3 rounded-md border text-left text-sm transition-colors ${
      current === value
        ? 'border-primary bg-primary/5 ring-1 ring-primary'
        : 'border-input hover:bg-accent'
    }`}
  >
    <div className="font-medium">{title}</div>
    <div className="text-xs text-muted-foreground mt-1">{desc}</div>
  </button>
);

// =============================================================
// FirewallPushCard - 单面墙的推送 Card
// =============================================================

interface FirewallPushCardProps {
  orderId: number;
  group: FirewallGroup;
  defaultMode: PushMode;
  effectiveMode: PushMode;
  wallOverride: PushMode | null;
  onSetOverride: (mode: PushMode | null) => void;
  batchQueryTrigger: number;
  onBatchQueryComplete: () => void;
  batchPushTrigger: number;
  batchPushTargetFwId: number | null;
  onDryRunLoaded: (fwId: number) => void;
  onBatchPushStart: (fwName: string) => void;
  onBatchPushDone: () => void;
}

const MODE_LABEL: Record<PushMode, string> = {
  deduplicate: '查重',
  force_push: '全推',
  reuse_objects: '对象复用',
};

const FirewallPushCard = ({
  orderId,
  group,
  defaultMode,
  effectiveMode,
  wallOverride,
  onSetOverride,
  batchQueryTrigger,
  onBatchQueryComplete,
  batchPushTrigger,
  batchPushTargetFwId,
  onDryRunLoaded,
  onBatchPushStart,
  onBatchPushDone,
}: FirewallPushCardProps) => {
  const fw = group.firewall;
  const startPushMutation = useStartPushV2(orderId);

  // 折叠: 命令预览 + 推送进度 (默认都折叠)
  const [scriptExpanded, setScriptExpanded] = useState(false);
  const [scriptData, setScriptData] = useState<GenerateScriptResponse | null>(
    null,
  );
  const [scriptLoading, setScriptLoading] = useState(false);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // 推送状态
  const [snapshotId, setSnapshotId] = useState<number | null>(null);
  const [pushing, setPushing] = useState(false);
  const [completed, setCompleted] = useState(false);

  const { data: snapshot } = useSnapshot(snapshotId);
  const { data: logsData } = useSnapshotLogs(
    snapshotId,
    pushing || completed,
    1500,
  );

  // snapshot 终态 → 推送结束
  useEffect(() => {
    if (
      snapshot &&
      (snapshot.status === 'success' ||
        snapshot.status === 'failed' ||
        snapshot.status === 'partial')
    ) {
      setPushing(false);
      setCompleted(true);
    }
  }, [snapshot]);

  // 批量 dry-run trigger 监听: 父组件 bump token → 本卡 force 加载
  const lastBatchTriggerProcessed = useRef(0);
  useEffect(() => {
    if (batchQueryTrigger === 0) return;
    if (batchQueryTrigger === lastBatchTriggerProcessed.current) return;
    lastBatchTriggerProcessed.current = batchQueryTrigger;
    void handleLoadScript('dry_run', { force: true }).then(() => onBatchQueryComplete());
  }, [batchQueryTrigger]);

  // 批量推送 trigger 监听: 父组件 bump token + 目标 fwId 匹配 → 本卡启动推送
  const lastBatchPushTriggerProcessed = useRef(0);
  useEffect(() => {
    if (batchPushTrigger === 0) return;
    if (batchPushTrigger === lastBatchPushTriggerProcessed.current) return;
    if (batchPushTargetFwId === null) return;
    if (batchPushTargetFwId !== fw.id) return;
    lastBatchPushTriggerProcessed.current = batchPushTrigger;
    onBatchPushStart(fw.name);
    void handleStart().then(() => onBatchPushDone());
  }, [batchPushTrigger, batchPushTargetFwId]);

  // 加载 generate-script (按需)
  // fetchMode: false = 本地 dry-run (NEW_RULE), true = 连墙拉配 (FULL_MATCH/TIME_UPDATE/NEW_RULE)
  const [fetchMode, setFetchMode] = useState<'dry_run' | 'deep'>('dry_run');
  const handleLoadScript = async (
    mode: 'dry_run' | 'deep' = 'dry_run',
    options?: { force?: boolean },
  ) => {
    // 同模式二次点击 → 折叠 (force 模式下跳过, 一键查询时强制刷新)
    if (
      !options?.force &&
      scriptData && scriptExpanded && fetchMode === mode
    ) {
      setScriptExpanded(false);
      return;
    }
    setFetchMode(mode);
    setScriptExpanded(true);
    setScriptLoading(true);
    setScriptError(null);
    setScriptData(null);
    try {
      const fetchParam = mode === 'deep' ? '&fetch_device_config=True' : '';
      const res = await fetch(
        `/api/push/orders/${orderId}/generate-script?firewall_id=${fw.id}${fetchParam}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as GenerateScriptResponse;
      setScriptData(data);
      // dry-run 成功 → 报告父组件 (用于"一键推送"前置条件校验)
      if (mode === 'dry_run') onDryRunLoaded(fw.id);
    } catch (e: any) {
      const msg = e?.message || String(e);
      setScriptError(msg);
      toast.apiError(e, '生成脚本失败');
    } finally {
      setScriptLoading(false);
    }
  };

  // 复制命令 (折叠区内的内联按钮) — 用 copyToClipboard helper 处理非安全上下文
  const handleCopy = async () => {
    if (!scriptData?.commands?.length) return;
    try {
      await copyToClipboard(scriptData.commands.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      toast.apiError(e, '复制失败');
    }
  };

  // 推送到这面墙
  const handleStart = async () => {
    if (group.policies.length === 0) {
      toast.warning('该防火墙没有可推送的策略');
      return;
    }
    setCompleted(false);
    setPushing(true);
    setSnapshotId(null);
    try {
      const result = await startPushMutation.mutateAsync({
        firewallId: fw.id,
        mode: effectiveMode,
      });
      if (result.snapshot_id) {
        setSnapshotId(result.snapshot_id);
      }
    } catch (error) {
      setPushing(false);
      toast.apiError(error, '启动推送失败');
    }
  };

  // 推送进度数据
  const total = snapshot?.total_policies ?? 0;
  const success = snapshot?.new_policies ?? 0;
  const failed = snapshot?.failed_policies ?? 0;
  const pending = Math.max(0, total - success - failed);
  const progress = total > 0 ? Math.round(((success + failed) / total) * 100) : 0;
  const logs = (logsData as PushLogsResponse | undefined)?.logs ?? [];

  return (
    <Card
      data-testid={`push-card-fw-${fw.id}`}
      className={completed && snapshot ? statusBorder(snapshot.status) : ''}
    >
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-xl flex items-center gap-2 flex-wrap">
              <Server className="h-4 w-4 flex-shrink-0" />
              {fw.name}
              {fw.alias && (
                <span className="text-sm text-muted-foreground font-normal">
                  ({fw.alias})
                </span>
              )}
              {fw.is_zone_boundary === 1 && (
                <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white">
                  <Send className="h-3 w-3 mr-1" />
                  将在此墙推送
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="mt-1">
              类型: <span className="font-mono">{fw.type}</span> · 管理 IP:{' '}
              <span className="font-mono">{fw.management_ip}</span> · 区域:{' '}
              {fw.belong_region || '未设置'} ·{' '}
              <span className="font-semibold">
                {group.policies.length} 条策略
              </span>
            </CardDescription>
          </div>
          {/* 推送按钮 + 模式提示 */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {!pushing && !completed && (
              <Button
                onClick={handleStart}
                disabled={startPushMutation.isPending}
                data-testid={`push-btn-fw-${fw.id}`}
              >
                <Play className="mr-2 h-4 w-4" />
                {startPushMutation.isPending ? '启动中...' : '推送到这面墙'}
              </Button>
            )}
            {completed && (
              <Button
                variant="outline"
                onClick={() => {
                  setCompleted(false);
                  setPushing(false);
                  setSnapshotId(null);
                }}
              >
                重新推送
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 本墙模式覆盖 (默认继承 defaultMode) */}
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span className="text-muted-foreground">本墙模式:</span>
          <select
            value={wallOverride ?? '__inherit__'}
            onChange={(e) => {
              const v = e.target.value;
              onSetOverride(v === '__inherit__' ? null : (v as PushMode));
            }}
            data-testid={`wall-mode-select-fw-${fw.id}`}
            className="border rounded px-2 py-1 bg-white"
          >
            <option value="__inherit__">继承默认 ({MODE_LABEL[defaultMode]})</option>
            <option value="deduplicate">查重模式</option>
            <option value="force_push">全推模式</option>
            <option value="reuse_objects">对象复用模式</option>
          </select>
          {wallOverride && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onSetOverride(null)}
              data-testid={`wall-mode-reset-fw-${fw.id}`}
            >
              <RotateCcw className="h-3 w-3 mr-1" />
              重置为默认
            </Button>
          )}
          {wallOverride && (
            <span className="text-amber-600">已覆盖默认</span>
          )}
        </div>

        {/* 当前模式提示 */}
        <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
          <Hash className="h-3 w-3" />
          推送模式: <span className="font-mono font-semibold">{effectiveMode}</span>
          {' · '}
          dry-run 是本地生成{effectiveMode === 'force_push' ? '' : ', 连墙深度分析会触发 SSH 拉配'}
        </div>

        {/* 脚本入口按钮 (dry-run 总是可见; 深度分析在 force_push 模式下隐藏) */}
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant={fetchMode === 'dry_run' && scriptExpanded ? 'default' : 'outline'}
            size="sm"
            onClick={() => handleLoadScript('dry_run')}
            data-testid={`script-toggle-dryrun-fw-${fw.id}`}
            title="本地生成命令, 不连设备, 所有策略都判 NEW_RULE"
          >
            <FileCode className="mr-2 h-4 w-4" />
            查看命令 (dry-run)
          </Button>
          {effectiveMode !== 'force_push' && (
            <Button
              variant={fetchMode === 'deep' && scriptExpanded ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleLoadScript('deep')}
              data-testid={`script-toggle-deep-fw-${fw.id}`}
              title="连墙拉配置, 走 PrePushAnalyzer 做 6 要素校验 (SSH 失败时 fallback)"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              深度分析 (连墙)
            </Button>
          )}
          {scriptData && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleLoadScript(fetchMode)}
              title="重新拉取"
            >
              <RotateCw className="mr-2 h-4 w-4" />
              刷新
            </Button>
          )}
        </div>

        {/* 命令预览 (折叠) */}
        {scriptExpanded && (
          <div className="mt-2 space-y-2 border rounded p-3 bg-slate-50/50">
            {scriptLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                <Loader2 className="h-4 w-4 animate-spin" />
                {fetchMode === 'deep' ? '正在连墙拉配置 + 6 要素分析...' : '正在生成脚本...'}
              </div>
            )}
            {scriptError && (
              <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold">生成失败</div>
                  <div>{scriptError}</div>
                </div>
              </div>
            )}
            {scriptData && (
              <>
                {/* 拉配状态提示 / 错误诊断 (deep 模式专属) */}
                {fetchMode === 'deep' && (
                  scriptData.device_config_fetched ? (
                    <div className="text-xs px-3 py-2 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 flex-shrink-0" />
                      <span>已连墙拉取真实配置, 6 要素分析基于设备现状</span>
                    </div>
                  ) : (
                    <DeepAnalysisError
                      fetchError={scriptData.fetch_error}
                      onSwitchToDryRun={() => handleLoadScript('dry_run')}
                      onRetry={() => handleLoadScript('deep')}
                    />
                  )
                )}

                {/* 6 卡片统计: full_match / time_update / new_rule + skipped / commands / total */}
                <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                  <MiniStat
                    label="完全复用"
                    value={scriptData.stats.full_match || 0}
                    color="emerald"
                  />
                  <MiniStat
                    label="时间联动"
                    value={scriptData.stats.time_update || 0}
                    color="amber"
                  />
                  <MiniStat
                    label="全新建"
                    value={scriptData.stats.new_rule || 0}
                    color="slate"
                  />
                  <MiniStat
                    label="工单策略"
                    value={scriptData.stats.total_order_policies}
                  />
                  <MiniStat
                    label="跳过"
                    value={scriptData.stats.skipped}
                    warn={scriptData.stats.skipped > 0}
                  />
                  <MiniStat
                    label="命令条数"
                    value={scriptData.stats.commands}
                    highlight
                  />
                </div>

                {/* 策略明细: 只显示复用的 (FULL_MATCH + TIME_UPDATE),
                    全新建 (NEW_RULE) 不展示, 实际命令在下方 "完整 CLI 命令" 块统一看 */}
                {(() => {
                  const allPolicies = scriptData.policies || scriptData.new_policies || [];
                  // 过滤: 复用类 (FULL_MATCH 完全复用, TIME_UPDATE 时间联动复用)
                  const reusedPolicies = allPolicies.filter(
                    (p) => p.match_mode !== 'NEW_RULE',
                  );
                  const newRuleCount = allPolicies.length - reusedPolicies.length;
                  return (
                    <div>
                      <div className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                        复用策略明细 ({reusedPolicies.length} 条)
                        {newRuleCount > 0 && (
                          <span className="text-xs text-muted-foreground font-normal">
                            · 另 {newRuleCount} 条全新建策略不展示
                          </span>
                        )}
                      </div>
                      <div className="space-y-1.5">
                        {reusedPolicies.map((pol, idx) => (
                          <PolicyAnalysisRow key={idx} policy={pol} />
                        ))}
                      </div>
                    </div>
                  );
                })()}

                {/* skipped 警告 */}
                {scriptData.skipped.length > 0 && (
                  <div className="p-2 bg-orange-50 border border-orange-200 rounded text-xs">
                    <div className="font-semibold text-orange-800 mb-1">
                      跳过 {scriptData.skipped.length} 条
                    </div>
                    <ul className="text-orange-700 space-y-0.5 max-h-24 overflow-auto">
                      {scriptData.skipped.map((s, i) => (
                        <li key={i}>
                          P{s.policy_id} {s.source_ip} → {s.dest_ip} — {s.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 黑色终端命令 (总体) */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-xs font-semibold text-slate-600">
                      完整 CLI 命令 ({scriptData.commands.length} 条)
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCopy}
                      disabled={!scriptData.commands.length}
                    >
                      {copied ? (
                        <>
                          <Check className="h-3 w-3 mr-1 text-green-600" />
                          已复制
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3 mr-1" />
                          复制
                        </>
                      )}
                    </Button>
                  </div>
                  <pre className="bg-slate-900 text-green-300 p-2 rounded font-mono text-xs leading-relaxed overflow-auto max-h-64 select-text">
                    {scriptData.commands.length === 0
                      ? '（无可生成命令, 全部 FULL_MATCH 跳过）'
                      : scriptData.commands.join('\n')}
                  </pre>
                </div>
              </>
            )}
          </div>
        )}

        {/* 推送中 / 完成: 进度 + 日志 */}
        {(pushing || completed) && snapshot && (
          <div className="space-y-3 pt-3 border-t">
            <PushProgressBar
              total={total}
              success={success}
              failed={failed}
              pending={pending}
              progress={progress}
              isProcessing={pushing}
            />
            {/* 模式提示 (跟 start-v2 用的 effectiveMode 一致) */}
            <div className="text-xs text-muted-foreground">
              模式: <span className="font-mono">{snapshot.push_mode}</span> · 批次:{' '}
              <span className="font-mono">
                {snapshot.batch_id.slice(0, 8)}
              </span>
            </div>
            {logs.length > 0 && <PushLogViewer logs={logs} />}
            {completed && snapshot.status !== 'success' && snapshot.error_log && (
              <div className="p-2 bg-red-50 border border-red-200 rounded text-xs">
                <div className="font-semibold text-red-700 mb-1">错误日志</div>
                <pre className="text-red-600 whitespace-pre-wrap font-mono text-xs">
                  {snapshot.error_log}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* 推送完成状态摘要 */}
        {completed && snapshot && (
          <div
            className={`p-2 rounded text-sm flex items-center gap-2 ${
              snapshot.status === 'success'
                ? 'bg-green-500/10 text-green-700'
                : snapshot.status === 'partial'
                ? 'bg-yellow-500/10 text-yellow-700'
                : 'bg-red-500/10 text-red-700'
            }`}
          >
            {snapshot.status === 'success' ? (
              <CheckCircle className="h-4 w-4" />
            ) : (
              <XCircle className="h-4 w-4" />
            )}
            <span className="font-semibold">
              {snapshot.status === 'success'
                ? '推送成功'
                : snapshot.status === 'partial'
                ? '部分成功'
                : '推送失败'}
            </span>
            <span className="text-xs">
              (新建 {snapshot.new_policies} / 复用 {snapshot.reused_policies} / 失败{' '}
              {snapshot.failed_policies} / 总 {snapshot.total_policies})
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// =============================================================
// 小工具
// =============================================================

const statusBorder = (s: string) => {
  switch (s) {
    case 'success':
      return 'border-green-500/50';
    case 'partial':
      return 'border-yellow-500/50';
    case 'failed':
      return 'border-red-500/50';
    default:
      return '';
  }
};

const MiniStat = ({
  label,
  value,
  highlight,
  warn,
  color,
}: {
  label: string;
  value: number;
  highlight?: boolean;
  warn?: boolean;
  color?: 'emerald' | 'amber' | 'slate';
}) => {
  // color prop 优先 (3 mode 用), 老 highlight/warn fallback
  const bgColor = color === 'emerald'
    ? 'border-emerald-300 bg-emerald-50'
    : color === 'amber'
    ? 'border-amber-300 bg-amber-50'
    : color === 'slate'
    ? 'border-slate-300 bg-slate-50'
    : warn
    ? 'border-orange-300 bg-orange-50'
    : highlight
    ? 'border-blue-300 bg-blue-50'
    : 'border-slate-200';
  const textColor = color === 'emerald'
    ? 'text-emerald-700'
    : color === 'amber'
    ? 'text-amber-700'
    : color === 'slate'
    ? 'text-slate-700'
    : warn ? 'text-orange-700' : highlight ? 'text-blue-700' : 'text-slate-800';
  return (
    <div className={`border rounded p-2 text-center ${bgColor}`}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-xl font-bold ${textColor}`}>{value}</div>
    </div>
  );
};

// =============================================================
// DeepAnalysisError - 深度分析错误诊断 + 操作建议
// =============================================================

interface DeepAnalysisErrorProps {
  fetchError: string | null | undefined;
  onSwitchToDryRun: () => void;
  onRetry: () => void;
}

interface ErrorDiagnosis {
  kind: 'no_credentials' | 'ssh_timeout' | 'ssh_failed' | 'parse_failed' | 'unknown';
  title: string;
  description: string;
  /** 操作建议列表 (空数组 = 无建议) */
  suggestions: { label: string; onClick: () => void; variant?: 'default' | 'outline' }[];
}

function diagnoseFetchError(msg: string | null | undefined, onSwitchToDryRun: () => void, onRetry: () => void): ErrorDiagnosis {
  if (!msg) {
    return {
      kind: 'unknown',
      title: '连墙分析失败',
      description: '未知错误, 请重试或切到 dry-run',
      suggestions: [
        { label: '切换到 dry-run', onClick: onSwitchToDryRun, variant: 'outline' },
        { label: '重试', onClick: onRetry },
      ],
    };
  }
  // 凭据缺失 (我 #2 commit 加的精准业务错)
  if (msg.includes('未配置 SSH 凭据') || msg.includes('缺 username/password')) {
    return {
      kind: 'no_credentials',
      title: '防火墙未配置 SSH 凭据',
      description: '深度分析需要 SSH 连墙拉配置, 请先在防火墙编辑页面配 username / password / port',
      suggestions: [
        { label: '切换到 dry-run (不连设备)', onClick: onSwitchToDryRun, variant: 'outline' },
        { label: '重试', onClick: onRetry, variant: 'outline' },
      ],
    };
  }
  // SSH timeout
  if (msg.includes('timed out') || msg.includes('timeout')) {
    return {
      kind: 'ssh_timeout',
      title: 'SSH 连接超时',
      description: '防火墙 IP/端口不可达或防火墙没启 SSH, 请检查网络和管理 IP 配置',
      suggestions: [
        { label: '切换到 dry-run', onClick: onSwitchToDryRun, variant: 'outline' },
        { label: '重试', onClick: onRetry },
      ],
    };
  }
  // SSH 一般错误 (认证失败 / 协议错误)
  if (msg.toLowerCase().includes('ssh') || msg.toLowerCase().includes('认证') || msg.toLowerCase().includes('auth')) {
    return {
      kind: 'ssh_failed',
      title: 'SSH 认证/连接失败',
      description: '请检查 username / password / port 是否正确, 防火墙是否允许 SSH',
      suggestions: [
        { label: '切换到 dry-run', onClick: onSwitchToDryRun, variant: 'outline' },
        { label: '重试', onClick: onRetry, variant: 'outline' },
      ],
    };
  }
  // 解析失败 (SSH 连上了但 parse_config 拿不到结构化数据)
  if (msg.includes('parse') || msg.includes('解析')) {
    return {
      kind: 'parse_failed',
      title: '设备配置解析失败',
      description: 'SSH 连接 OK 但解析配置文本失败, 可能是设备型号不被支持或配置异常',
      suggestions: [
        { label: '切换到 dry-run', onClick: onSwitchToDryRun, variant: 'outline' },
        { label: '重试', onClick: onRetry, variant: 'outline' },
      ],
    };
  }
  // 未知 (原文)
  return {
    kind: 'unknown',
    title: '连墙分析失败',
    description: msg,
    suggestions: [
      { label: '切换到 dry-run', onClick: onSwitchToDryRun, variant: 'outline' },
      { label: '重试', onClick: onRetry },
    ],
  };
}

const DeepAnalysisError = ({ fetchError, onSwitchToDryRun, onRetry }: DeepAnalysisErrorProps) => {
  const diag = diagnoseFetchError(fetchError, onSwitchToDryRun, onRetry);
  return (
    <div className="text-sm px-3 py-2.5 rounded bg-yellow-50 text-yellow-800 border border-yellow-300 space-y-1.5">
      <div className="flex items-start gap-2">
        <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="font-semibold">{diag.title}</div>
          <div className="text-xs text-yellow-700 mt-0.5">{diag.description}</div>
        </div>
      </div>
      <div className="text-xs text-yellow-700 font-mono bg-yellow-100 px-2 py-1 rounded break-all">
        错误: {fetchError || '(无详细信息)'}
      </div>
      <div className="flex items-center gap-2 flex-wrap pt-1">
        {diag.suggestions.map((s, i) => (
          <Button
            key={i}
            variant={s.variant || 'default'}
            size="sm"
            onClick={s.onClick}
            data-testid={`deep-error-${diag.kind}-action-${i}`}
          >
            {s.label}
          </Button>
        ))}
      </div>
    </div>
  );
};

// =============================================================
// PolicyAnalysisRow - 策略明细单行
// =============================================================

interface PolicyAnalysisRowProps {
  policy: GenerateScriptNewPolicy;
}

const PolicyAnalysisRow = ({ policy }: PolicyAnalysisRowProps) => {
  // 命令本身在墙级 "完整 CLI 命令" 块统一展示, 这里只展示复用相关匹配信息
  // (NEW_RULE 已在策略明细区被过滤掉, 这里只剩 FULL_MATCH / TIME_UPDATE)
  const mode = (policy.match_mode || 'NEW_RULE') as MatchMode;
  const script = policy.push_script || [];
  const scriptCommandCount = script.length; // 仅供参考 (用户去墙级块复制命令)

  // 边框颜色跟 match_mode 走
  const borderClass = mode === 'FULL_MATCH'
    ? 'border-l-4 border-l-emerald-500 border-emerald-200'
    : mode === 'TIME_UPDATE'
    ? 'border-l-4 border-l-amber-500 border-amber-200'
    : 'border-l-4 border-l-slate-400 border-slate-200';

  return (
    <div
      className={`bg-white rounded p-2 ${borderClass}`}
      data-testid={`policy-row-${policy.policy_id}-${mode.toLowerCase()}`}
    >
      <div className="flex items-start gap-2 flex-wrap">
        <div className="flex-1 min-w-0 space-y-1">
          {/* match badge + rule_name + 概要 */}
          <div className="flex items-center gap-2 flex-wrap">
            <PolicyMatchBadge mode={mode} ruleName={policy.reused_rule_name} size="sm" />
            <span className="text-xs text-muted-foreground font-mono">
              {policy.rule_name}
            </span>
            <span className="text-xs text-slate-600">
              {policy.src_ips?.join(', ')} → {policy.dst_ips?.join(', ')}
              {policy.ports?.length ? ` : ${policy.ports.join(' ')}` : ''}
            </span>
          </div>
          {/* 复用信息 */}
          {policy.reused_rule_content && (
            <div className="text-xs text-slate-600 font-mono bg-slate-50 px-2 py-1 rounded">
              <span className="font-semibold text-slate-700">复用:</span>{' '}
              {policy.reused_rule_content}
            </div>
          )}
          {/* audit_message */}
          {policy.audit_message && (
            <div className="text-xs text-slate-500 italic">
              {policy.audit_message}
            </div>
          )}
          {/* 命令条数提示 (墙视角, 实际命令在下方 "完整 CLI 命令" 块) */}
          {scriptCommandCount > 0 && (
            <div className="text-xs text-muted-foreground">
              → 将生成 <span className="font-mono font-semibold">{scriptCommandCount}</span> 条命令
            </div>
          )}
        </div>
      </div>
    </div>
  );
};


// =============================================================
// BatchPushConfirmModal - 一键推送确认弹窗
// =============================================================

interface BatchPushConfirmModalProps {
  previewData: PreviewData;
  defaultMode: PushMode;
  wallModeOverrides: Record<number, PushMode>;
  onConfirm: () => void;
  onCancel: () => void;
}

const BatchPushConfirmModal = ({
  previewData,
  defaultMode,
  wallModeOverrides,
  onConfirm,
  onCancel,
}: BatchPushConfirmModalProps) => {
  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onCancel}
      data-testid="batch-push-confirm-modal"
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div className="flex items-center gap-2">
            <Play className="h-5 w-5 text-slate-600" />
            <h2 className="text-lg font-semibold">确认批量推送</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={onCancel} aria-label="关闭">
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-5 py-4 space-y-3">
          <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded text-amber-700 text-sm">
            <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold">即将串行推送到 {previewData.firewall_groups.length} 面墙</div>
              <div className="text-xs mt-1">
                推送按 firewall_groups 顺序执行 (前一面完成 SSH + 落库后开始下一面), 单墙失败不中断后续墙。
                dry-run 命令已在每面墙的折叠区查看过。
              </div>
            </div>
          </div>

          <div className="border rounded overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-100">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">防火墙</th>
                  <th className="px-3 py-2 text-left font-medium">管理 IP</th>
                  <th className="px-3 py-2 text-left font-medium">模式</th>
                  <th className="px-3 py-2 text-right font-medium">策略数</th>
                </tr>
              </thead>
              <tbody>
                {previewData.firewall_groups.map((g) => {
                  const fw = g.firewall;
                  const mode = wallModeOverrides[fw.id] ?? defaultMode;
                  const overridden = wallModeOverrides[fw.id] != null;
                  return (
                    <tr key={fw.id} className="border-t">
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <Server className="h-3 w-3 text-slate-400" />
                          <span className="font-mono text-xs">{fw.name}</span>
                          {overridden && (
                            <span className="text-amber-600 text-xs">(已覆盖默认)</span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-slate-600">
                        {fw.management_ip}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{mode}</td>
                      <td className="px-3 py-2 text-right font-mono">
                        {g.policies.length}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t bg-slate-50">
          <Button variant="outline" onClick={onCancel}>
            取消
          </Button>
          <Button
            onClick={onConfirm}
            data-testid="batch-push-confirm-btn"
          >
            <Play className="mr-2 h-4 w-4" />
            确认推送 {previewData.firewall_groups.length} 面墙
          </Button>
        </div>
      </div>
    </div>
  );
};
