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
import { useState, useEffect } from 'react';
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
  Send,
  Loader2,
  RotateCw,
  Sparkles,
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
import type { PushMode, PushLogsResponse } from '../lib/api';
import { toast } from '../lib/toast';
import type {
  PreviewData,
  FirewallGroup,
  GenerateScriptResponse,
  GenerateScriptNewPolicy,
} from '../types/preview';

export const Push = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const oid = Number(orderId);

  // 全局推送模式 (3 模式 Radio, 共享给所有墙)
  const [mode, setMode] = useState<PushMode>('deduplicate');

  // preview 数据
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(true);

  // 拉 preview
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoadingPreview(true);
        const res = await fetch(`/api/workorders/${oid}/preview`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as PreviewData;
        if (!cancelled) setPreviewData(data);
      } catch (e) {
        if (!cancelled) toast.apiError(e, '加载预览数据失败');
      } finally {
        if (!cancelled) setLoadingPreview(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [oid]);

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

      {/* 顶部全局: 3 模式 Radio (适用于所有墙) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Hash className="h-4 w-4" />
            推送模式 (适用于所有墙)
          </CardTitle>
          <CardDescription>
            选好后, 每面墙的"推送到这面墙"按钮会用这个模式调用 start-v2
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <ModeRadio
              current={mode}
              value="deduplicate"
              title="查重模式"
              desc="复用整条已存在策略，对象不重用才新建"
              onChange={setMode}
            />
            <ModeRadio
              current={mode}
              value="force_push"
              title="全推模式"
              desc="对象与策略全错开新建（强制落盘）"
              onChange={setMode}
            />
            <ModeRadio
              current={mode}
              value="reuse_objects"
              title="对象复用模式"
              desc="复用相同 IP/端口组，策略行新建"
              onChange={setMode}
            />
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
        previewData.firewall_groups.map((group) => (
          <FirewallPushCard
            key={group.firewall.id}
            orderId={oid}
            group={group}
            mode={mode}
          />
        ))
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
  mode: PushMode;
}

const FirewallPushCard = ({ orderId, group, mode }: FirewallPushCardProps) => {
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

  // 加载 generate-script (按需)
  // fetchMode: false = 本地 dry-run (NEW_RULE), true = 连墙拉配 (FULL_MATCH/TIME_UPDATE/NEW_RULE)
  const [fetchMode, setFetchMode] = useState<'dry_run' | 'deep'>('dry_run');
  const handleLoadScript = async (mode: 'dry_run' | 'deep' = 'dry_run') => {
    // 同模式二次点击 → 折叠
    if (scriptData && scriptExpanded && fetchMode === mode) {
      setScriptExpanded(false);
      return;
    }
    setFetchMode(mode);
    setScriptExpanded(true);
    setScriptLoading(true);
    setScriptError(null);
    setScriptData(null);  // 强制重新 fetch (模式不同)
    try {
      const fetchParam = mode === 'deep' ? '&fetch_device_config=True' : '';
      const res = await fetch(
        `/api/push/orders/${orderId}/generate-script?firewall_id=${fw.id}${fetchParam}`,
        { method: 'POST' },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      const data = (await res.json()) as GenerateScriptResponse;
      setScriptData(data);
    } catch (e) {
      const msg = e instanceof Error ? e.message : '加载失败';
      setScriptError(msg);
      toast.apiError(e, '生成命令失败');
    } finally {
      setScriptLoading(false);
    }
  };

  // 复制命令
  const handleCopy = async () => {
    if (!scriptData?.commands?.length) return;
    try {
      await navigator.clipboard.writeText(scriptData.commands.join('\n'));
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
        mode,
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
        {/* 当前模式提示 */}
        <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
          <Hash className="h-3 w-3" />
          推送模式: <span className="font-mono font-semibold">{mode}</span>
          {' · '}
          dry-run (NEW_RULE) 是本地生成, 连墙深度分析会触发 SSH 拉配
        </div>

        {/* 2 个脚本入口按钮 (toggle) */}
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

                {/* 策略明细: 每条带 match badge + 复用信息 + push_script */}
                {(scriptData.policies || scriptData.new_policies || []).length > 0 && (
                  <div>
                    <div className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                      策略明细 ({(scriptData.policies || scriptData.new_policies || []).length} 条)
                    </div>
                    <div className="space-y-1.5">
                      {(scriptData.policies || scriptData.new_policies || []).map(
                        (pol, idx) => (
                          <PolicyAnalysisRow key={idx} policy={pol} />
                        ),
                      )}
                    </div>
                  </div>
                )}

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
            {/* 模式提示 (跟 start-v2 用的 mode 一致) */}
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
  const [copied, setCopied] = useState(false);
  const mode = (policy.match_mode || 'NEW_RULE') as MatchMode;
  const script = policy.push_script || [];
  const hasScript = script.length > 0;

  const handleCopy = async () => {
    if (!hasScript) return;
    try {
      await navigator.clipboard.writeText(script.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      toast.apiError(e, '复制失败');
    }
  };

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
      <div className="flex items-start justify-between gap-2 flex-wrap">
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
        </div>
        {/* push_script 复制按钮 */}
        {hasScript && (
          <Button variant="outline" size="sm" onClick={handleCopy} className="flex-shrink-0">
            {copied ? (
              <>
                <Check className="h-3 w-3 mr-1 text-green-600" />
                已复制
              </>
            ) : (
              <>
                <Copy className="h-3 w-3 mr-1" />
                复制脚本 ({script.length})
              </>
            )}
          </Button>
        )}
      </div>
      {/* push_script 文本域 */}
      {hasScript && (
        <pre className="mt-2 bg-slate-900 text-green-300 p-2 rounded font-mono text-xs leading-relaxed overflow-auto max-h-32 select-text">
          {script.join('\n')}
        </pre>
      )}
      {mode === 'FULL_MATCH' && !hasScript && (
        <div className="mt-1 text-xs text-emerald-600 italic">
          ✓ 各要素均已被包容, 无需下发任何命令
        </div>
      )}
    </div>
  );
};
