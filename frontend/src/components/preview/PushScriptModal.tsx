/**
 * 推送脚本弹窗（dry-run）
 *
 * 父组件传 orderId + firewall，弹窗自己 fetch
 *   POST /api/push/orders/{orderId}/generate-script?firewall_id={firewall.id}
 * 展示 stats + commands 列表 + 一键复制 + skipped 警告（如果有）。
 *
 * 设计原则（按 SKILL 坑点 13 — 父编排, 子展示）：
 * - Dumb component, 内部 useState/useEffect 管 loading/data/error
 * - 父组件不感知 fetch 细节
 * - 按 ESC 关闭 + 点 backdrop 关闭
 */
import { useEffect, useState } from 'react';
import { X, Copy, Check, AlertCircle, FileCode } from 'lucide-react';
import { Button } from '../ui/Button';
import { toast } from '../../lib/toast';
import type {
  GenerateScriptResponse,
  PreviewFirewall,
} from '../../types/preview';

interface PushScriptModalProps {
  orderId: number;
  firewall: PreviewFirewall;
  onClose: () => void;
}

export const PushScriptModal = ({
  orderId,
  firewall,
  onClose,
}: PushScriptModalProps) => {
  const [data, setData] = useState<GenerateScriptResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showNewPolicies, setShowNewPolicies] = useState(false);

  // 打开时拉数据
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(
          `/api/push/orders/${orderId}/generate-script?firewall_id=${firewall.id}`,
          { method: 'POST' },
        );
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.detail || `HTTP ${res.status}`);
        }
        const body = (await res.json()) as GenerateScriptResponse;
        if (!cancelled) setData(body);
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : '加载失败';
          setError(msg);
          toast.apiError(e, '生成推送脚本失败');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [orderId, firewall.id]);

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleCopy = async () => {
    if (!data?.commands?.length) return;
    try {
      await navigator.clipboard.writeText(data.commands.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      toast.apiError(e, '复制失败');
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b">
          <div className="flex items-center gap-2">
            <FileCode className="h-5 w-5 text-slate-600" />
            <h2 className="text-lg font-semibold">
              推送脚本
              <span className="text-sm text-muted-foreground ml-2 font-normal">
                {firewall.name} · {firewall.type} · {firewall.management_ip}
              </span>
            </h2>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="关闭">
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
          {loading && (
            <div className="text-center py-12 text-muted-foreground">
              正在生成脚本（不连设备，本地 dry-run）…
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded text-red-700">
              <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold">生成失败</div>
                <div className="text-sm">{error}</div>
              </div>
            </div>
          )}

          {data && (
            <>
              {/* Stats 4 卡片 */}
              <div className="grid grid-cols-4 gap-3">
                <StatCard label="工单策略" value={data.stats.total_order_policies} />
                <StatCard label="可推送" value={data.stats.to_push} highlight />
                <StatCard label="跳过" value={data.stats.skipped} warn={data.stats.skipped > 0} />
                <StatCard label="命令条数" value={data.stats.commands} highlight />
              </div>

              {/* Skipped 警告 */}
              {data.skipped.length > 0 && (
                <div className="p-3 bg-orange-50 border border-orange-200 rounded">
                  <div className="font-semibold text-orange-800 mb-1 text-sm">
                    跳过 {data.skipped.length} 条
                  </div>
                  <ul className="text-xs text-orange-700 space-y-0.5 max-h-32 overflow-auto">
                    {data.skipped.map((s, i) => (
                      <li key={i}>
                        P{s.policy_id} {s.source_ip} → {s.dest_ip} — {s.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Commands 区（黑底终端） */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm font-semibold text-slate-700">
                    CLI 命令
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopy}
                    disabled={!data.commands.length}
                  >
                    {copied ? (
                      <>
                        <Check className="h-4 w-4 mr-1 text-green-600" />
                        已复制
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4 mr-1" />
                        复制全部
                      </>
                    )}
                  </Button>
                </div>
                <pre className="bg-slate-900 text-green-300 p-3 rounded font-mono text-xs leading-relaxed overflow-auto max-h-96 select-text">
                  {data.commands.length === 0
                    ? '（无可生成命令）'
                    : data.commands.join('\n')}
                </pre>
              </div>

              {/* New policies 折叠区 */}
              {data.new_policies.length > 0 && (
                <div>
                  <button
                    onClick={() => setShowNewPolicies((v) => !v)}
                    className="text-sm font-semibold text-slate-700 hover:text-slate-900 cursor-pointer"
                  >
                    {showNewPolicies ? '▼' : '▶'} 生成的策略明细（{data.new_policies.length}）
                  </button>
                  {showNewPolicies && (
                    <div className="mt-2 border rounded overflow-auto max-h-48">
                      <table className="w-full text-xs">
                        <thead className="bg-slate-100 sticky top-0">
                          <tr>
                            <th className="px-2 py-1 text-left">Rule</th>
                            <th className="px-2 py-1 text-left">源</th>
                            <th className="px-2 py-1 text-left">目的</th>
                            <th className="px-2 py-1 text-left">端口</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.new_policies.map((p, i) => (
                            <tr key={i} className="border-t">
                              <td className="px-2 py-1 font-mono">{p.rule_name}</td>
                              <td className="px-2 py-1">
                                <div>{p.src_zone}</div>
                                <div className="text-muted-foreground font-mono">
                                  {p.src_ips.join(', ')}
                                </div>
                              </td>
                              <td className="px-2 py-1">
                                <div>{p.dst_zone}</div>
                                <div className="text-muted-foreground font-mono">
                                  {p.dst_ips.join(', ')}
                                </div>
                              </td>
                              <td className="px-2 py-1 font-mono">
                                {p.ports.join(', ')}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const StatCard = ({
  label,
  value,
  highlight,
  warn,
}: {
  label: string;
  value: number;
  highlight?: boolean;
  warn?: boolean;
}) => (
  <div
    className={`border rounded p-2 text-center ${
      warn
        ? 'border-orange-300 bg-orange-50'
        : highlight
        ? 'border-blue-300 bg-blue-50'
        : 'border-slate-200'
    }`}
  >
    <div className="text-xs text-muted-foreground">{label}</div>
    <div
      className={`text-2xl font-bold ${
        warn ? 'text-orange-700' : highlight ? 'text-blue-700' : 'text-slate-800'
      }`}
    >
      {value}
    </div>
  </div>
);
