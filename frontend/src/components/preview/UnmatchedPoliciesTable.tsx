import type { PreviewPolicy } from '../../types';

interface Props {
  policies: PreviewPolicy[];
}

/**
 * "异常提示" → "未匹配防火墙的策略" 表格
 *
 * 列宽规范见 SKILL.md 坑点 9 (table-fixed + colgroup + truncate + title)
 *
 * 单独拆出来便于:
 *   - 单独 unit test 渲染
 *   - 以后做导出/筛选/搜索等扩展不影响父级 Preview
 */
export const UnmatchedPoliciesTable = ({ policies }: Props) => {
  if (policies.length === 0) return null;

  return (
    <div className="border rounded-lg overflow-hidden mt-2">
      <table className="w-full text-sm table-fixed">
        <colgroup>
          <col className="w-12" />      {/* 序号 */}
          <col className="w-48" />     {/* 源IP */}
          <col className="w-48" />     {/* 目的IP */}
          <col className="w-32" />     {/* 服务/端口 */}
          <col className="w-32" />     {/* 时间 */}
          <col />                      {/* 原因 (占剩余宽度) */}
        </colgroup>
        <thead className="bg-orange-100">
          <tr>
            <th className="px-3 py-2 text-left">序号</th>
            <th className="px-3 py-2 text-left">源IP</th>
            <th className="px-3 py-2 text-left">目的IP</th>
            <th className="px-3 py-2 text-left">服务/端口</th>
            <th className="px-3 py-2 text-left">时间</th>
            <th className="px-3 py-2 text-left">原因</th>
          </tr>
        </thead>
        <tbody>
          {policies.map((policy) => (
            <tr key={policy.id} className="border-t">
              <td className="px-3 py-2 font-semibold text-center truncate">{policy.sequence}</td>
              <td className="px-3 py-2 whitespace-pre-line break-all">{policy.source_ip}</td>
              <td className="px-3 py-2 whitespace-pre-line break-all">{policy.dest_ip}</td>
              <td className="px-3 py-2 whitespace-pre-line break-all">{policy.service}</td>
              <td className="px-3 py-2 truncate" title={policy.使用时间}>{policy.使用时间 || '\u00A0'}</td>
              <td className="px-3 py-2 text-orange-600">{policy.not_pushed_reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
