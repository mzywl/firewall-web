/**
 * PolicyMatchBadge - 3 mode 单条策略归宿徽章
 *
 * 3 种归宿 (跟后端 PrePushAnalyzer 对齐):
 *   - FULL_MATCH (绿): 完全复用老策略, 本次下发跳过
 *   - TIME_UPDATE (黄): 网络资产落入老策略, 仅需改时间
 *   - NEW_RULE (灰): 未匹配, 全新建
 *
 * 用法:
 *   <PolicyMatchBadge mode="FULL_MATCH" ruleName="Rule_Sec_Prod" />
 */
import { CheckCircle, Clock, Plus } from 'lucide-react';
import { Badge } from '../ui/Badge';

export type MatchMode = 'FULL_MATCH' | 'TIME_UPDATE' | 'NEW_RULE';

interface PolicyMatchBadgeProps {
  mode: MatchMode;
  ruleName?: string | null;
  /** size: sm (默认, 表格行内) | md (详情区, 大) */
  size?: 'sm' | 'md';
}

const META: Record<MatchMode, {
  label: string;
  bgClass: string;
  textClass: string;
  iconClass: string;
  Icon: typeof CheckCircle;
}> = {
  FULL_MATCH: {
    label: '完全复用',
    bgClass: 'bg-emerald-500 hover:bg-emerald-600',
    textClass: 'text-white',
    iconClass: 'text-white',
    Icon: CheckCircle,
  },
  TIME_UPDATE: {
    label: '时间联动扩展',
    bgClass: 'bg-amber-500 hover:bg-amber-600',
    textClass: 'text-white',
    iconClass: 'text-white',
    Icon: Clock,
  },
  NEW_RULE: {
    label: '全新建',
    bgClass: 'bg-slate-400 hover:bg-slate-500',
    textClass: 'text-white',
    iconClass: 'text-white',
    Icon: Plus,
  },
};

export const PolicyMatchBadge = ({ mode, ruleName, size = 'sm' }: PolicyMatchBadgeProps) => {
  const meta = META[mode] || META.NEW_RULE;
  const { Icon } = meta;
  const iconSize = size === 'sm' ? 'h-3 w-3' : 'h-4 w-4';
  const padding = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-1';
  return (
    <Badge
      className={`${meta.bgClass} ${meta.textClass} ${padding} inline-flex items-center gap-1 whitespace-nowrap`}
      title={
        mode === 'FULL_MATCH' && ruleName
          ? `完全复用: ${ruleName}`
          : mode === 'TIME_UPDATE' && ruleName
          ? `时间联动: ${ruleName}`
          : '未匹配老策略, 全新建'
      }
      data-testid={`match-badge-${mode.toLowerCase()}-${ruleName || 'unknown'}`}
    >
      <Icon className={iconSize} />
      {meta.label}
      {ruleName && size === 'md' && (
        <span className="ml-1 font-mono opacity-90">[{ruleName}]</span>
      )}
    </Badge>
  );
};
