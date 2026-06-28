import { Fragment } from 'react';
import { Info, AlertTriangle, Trash2, Undo2 } from 'lucide-react';
import type { FirewallGroup } from '../../types';

interface Props {
  group: FirewallGroup;
  /**
   * 切换单行的 is_ignored 状态 (Execution Plan 架构, 2026-06-28)
   * - rowUuid: 后端给每行分配的 UUID
   * - currentIgnoreStatus: 当前 is_ignored 值 (用于前端判断调用时传 !currentIgnoreStatus)
   */
  onToggleIgnore?: (rowUuid: string, currentIgnoreStatus: boolean) => void;
}

/**
 * 单个防火墙组的策略表格
 *
 * Execution Plan 架构 (2026-06-28):
 *   - 拿后端 plan_data 直接渲染, 不再做原始表格比对
 *   - 每行带 row_uuid (后端 uuid.uuid4()) 作为 React key + 操作寻址
 *   - is_ignored=true: 行变灰 (opacity-50), 按钮切到 "恢复" (蓝)
 *   - is_ignored=false: 正常样式, 按钮是 "删除" (红)
 *   - NAT 行跟随父行的 is_ignored 自然变灰 (同一 <tr> 内 fragment 嵌套)
 *
 * 包含:
 *   - 原始策略行 (is_ignored 时 opacity-50)
 *   - SNAT 转换行 (蓝色, source_ip 替换为 snat_address)
 *   - PASS_THROUGH 透传行 (绿色, 标记 via_firewall + 原 src= 显示)
 *   - NAT 警告行 (黄色)
 *   - 删除/恢复按钮 (右侧操作列, 调 onToggleIgnore 回调)
 *
 * 坑点 (列宽规范): table-fixed + colgroup + truncate + title, 详见 SKILL.md 坑点 9
 * 坑点 (zone 双轨): nat_info.source_zone (程序) / source_zone_name (业务名), UI 用 *_zone_name
 */
export const FirewallPolicyTable = ({ group, onToggleIgnore }: Props) => {
  return (
    <div className="border rounded-lg overflow-hidden">
      <table className="w-full text-sm table-fixed">
        <colgroup>
          <col className="w-12" /> {/* 序号 */}
          <col className="w-24" /> {/* 源区域 (internal/external) */}
          <col className="w-48" /> {/* 源IP */}
          <col className="w-24" /> {/* 目的区域 */}
          <col className="w-48" /> {/* 目的IP */}
          <col className="w-32" /> {/* 服务/端口 */}
          <col className="w-32" /> {/* 时间 */}
          <col /> {/* NAT (占剩余) */}
          <col className="w-20" /> {/* 操作 (删除/恢复) */}
        </colgroup>
        <thead className="bg-muted">
          <tr>
            <th className="px-3 py-2 text-left">序号</th>
            <th className="px-3 py-2 text-left">源区域</th>
            <th className="px-3 py-2 text-left">源IP</th>
            <th className="px-3 py-2 text-left">目的区域</th>
            <th className="px-3 py-2 text-left">目的IP</th>
            <th className="px-3 py-2 text-left">服务/端口</th>
            <th className="px-3 py-2 text-left">时间</th>
            <th className="px-3 py-2 text-left">NAT</th>
            <th className="px-3 py-2 text-left">操作</th>
          </tr>
        </thead>
        <tbody>
          {group.policies.map((policy) => {
            // 整行 (含 NAT 子行 + warnings 行) 跟着 is_ignored 变灰
            // 用 fragment 包裹多个 <tr>, 父 <tr> 的 className 由 React 应用
            const rowBaseClass = policy.is_ignored
              ? 'opacity-50 bg-gray-50 hover:bg-gray-100'
              : 'hover:bg-muted/50';
            return (
            <Fragment key={policy.row_uuid || policy.id || policy.original_policy_id}>
              {/* 原始策略行 */}
              <tr className={`border-t ${rowBaseClass}`}>
                <td className="px-3 py-2 font-semibold text-center truncate">{policy.sequence}</td>
                <td className="px-3 py-2 truncate" title={policy.nat_info.source_zone_name || policy.nat_info.source_zone || ''}>
                  {policy.nat_info.source_zone_name || policy.nat_info.source_zone || '-'}
                </td>
                <td className="px-3 py-2 whitespace-pre-line break-all">{policy.source_ip}</td>
                <td className="px-3 py-2 truncate" title={policy.nat_info.dest_zone_name || policy.nat_info.dest_zone || ''}>
                  {policy.nat_info.dest_zone_name || policy.nat_info.dest_zone || '-'}
                </td>
                <td className="px-3 py-2 whitespace-pre-line break-all">{policy.dest_ip}</td>
                <td className="px-3 py-2 whitespace-pre-line break-all">{policy.service}</td>
                <td className="px-3 py-2 truncate" title={policy.使用时间}>{policy.使用时间 || '\u00A0'}</td>
                <td className="px-3 py-2">
                  {policy.nat_info.need_nat ? (
                    <div className="flex items-center gap-1">
                      <Info className="h-4 w-4 text-blue-500" />
                      <span className="text-blue-600 font-medium">
                        {policy.nat_info.nat_type}
                      </span>
                    </div>
                  ) : (
                    <span className="text-gray-400">无需NAT</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {onToggleIgnore && policy.row_uuid && (
                    policy.is_ignored ? (
                      // 变灰状态: 蓝色 "恢复" 按钮 (Undo2 图标)
                      <button
                        type="button"
                        onClick={() => onToggleIgnore(policy.row_uuid, true)}
                        className="text-blue-500 hover:text-blue-700 hover:bg-blue-50 rounded p-1 inline-flex items-center"
                        title="恢复该策略 (commit 时会重新入库推送)"
                        data-testid={`restore-policy-${policy.row_uuid}`}
                      >
                        <Undo2 className="h-4 w-4" />
                      </button>
                    ) : (
                      // 正常状态: 红色 "删除" 按钮 (Trash2 图标)
                      <button
                        type="button"
                        onClick={() => onToggleIgnore(policy.row_uuid, false)}
                        className="text-red-500 hover:text-red-700 hover:bg-red-50 rounded p-1 inline-flex items-center"
                        title="从工单中忽略该策略 (commit 时不入库)"
                        data-testid={`delete-policy-${policy.row_uuid}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )
                  )}
                </td>
              </tr>

              {/* NAT 转换 / 透传行 (跟随父行 is_ignored 自然变灰) */}
              {policy.nat_policies.map((natPolicy, idx) => {
                const isPassThrough = natPolicy.type === 'PASS_THROUGH'
                const rowBg = isPassThrough ? 'bg-emerald-50' : 'bg-blue-50'
                const textColor = isPassThrough ? 'text-emerald-700' : 'text-blue-700'
                const badgeBg = isPassThrough ? 'bg-emerald-200 text-emerald-800' : 'bg-blue-200 text-blue-800'
                const labelText = isPassThrough
                  ? `[经 ${natPolicy.via_firewall?.name || '前序墙'} SNAT 转换]`
                  : '[SNAT]'
                // PASS_THROUGH 行的 source_ip 已是 SNAT 后的地址, 原始 IP 在 original_source_ip
                // 仅当两者不同才显示 "原 src=..." 让用户看到流量从哪个 IP 透传过来
                const showOriginalSrc = isPassThrough
                  && natPolicy.original_source_ip
                  && natPolicy.original_source_ip !== natPolicy.source_ip
                return (
                  <tr key={`${policy.row_uuid || policy.id}-nat-${idx}`} className={`border-t ${rowBg}`}>
                    <td className="px-3 py-2"></td>
                    <td className={`px-3 py-2 ${textColor} truncate`}>{natPolicy.source_zone}</td>
                    <td className={`px-3 py-2 ${textColor} whitespace-pre-line break-all`}>
                      {natPolicy.source_ip}
                      <span className={`ml-2 px-2 py-0.5 ${badgeBg} text-xs rounded`}>
                        {labelText}
                      </span>
                      {showOriginalSrc && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          原 src={natPolicy.original_source_ip}
                        </span>
                      )}
                    </td>
                    <td className={`px-3 py-2 ${textColor} truncate`}>{natPolicy.dest_zone}</td>
                    <td className={`px-3 py-2 ${textColor} whitespace-pre-line break-all`}>{natPolicy.dest_ip}</td>
                    <td className={`px-3 py-2 ${textColor} whitespace-pre-line break-all`}>{natPolicy.service}</td>
                    <td className="px-3 py-2"></td>
                    <td className="px-3 py-2">
                      <span className={`text-xs ${isPassThrough ? 'text-emerald-600' : 'text-blue-600'}`}>
                        {isPassThrough ? '透传后' : '转换后'}
                      </span>
                    </td>
                    <td className="px-3 py-2"></td>
                  </tr>
                )
              })}

              {/* NAT 警告行 */}
              {policy.nat_info.warnings.length > 0 && (
                <tr className="border-t bg-yellow-50">
                  <td colSpan={9} className="px-4 py-2">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5" />
                      <div className="text-sm text-yellow-700">
                        {policy.nat_info.warnings.join('; ')}
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  );
};
