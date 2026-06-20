import { useRef, useEffect, useCallback, useState } from 'react';
import type { Policy } from '../../types';
import { useSyncScroll } from '../../hooks/useSyncScroll';

interface BaseProps {
  onUpdate?: (policies: Policy[]) => void;
  loading?: boolean;
}

interface DualProps extends BaseProps {
  mode?: 'dual';
  topPolicies: Policy[];
  bottomPolicies: Policy[];
  /** @deprecated 标题由外层 Card 渲染,组件内部不再写死 */
  topTitle?: never;
  bottomTitle?: never;
}

interface SingleProps extends BaseProps {
  mode: 'single';
  policies: Policy[];
  editable?: boolean;
  title?: string;
}

type SyncScrollTableProps = DualProps | SingleProps;

// 固定列顺序和列宽配置（使用 Excel 原始中文字段名）
const COLUMNS = [
  { key: '源端系统-环境-用途', label: '源端系统-环境-用途', width: '200px' },
  { key: '源IP', label: '源IP', width: '180px' },
  { key: '目的端系统-环境-用途', label: '目的端系统-环境-用途', width: '200px' },
  { key: '目的IP', label: '目的IP', width: '180px' },
  { key: '目的端口', label: '目的端口', width: '120px' },
  { key: '使用时间', label: '使用时间', width: '120px' },
];

export const SyncScrollTable = (props: SyncScrollTableProps) => {
  // dual 模式默认; single 模式用 policies / editable
  const isSingle = props.mode === 'single';
  const loading = props.loading ?? false;
  const onUpdate = props.onUpdate;

  const topScrollRef = useRef<HTMLDivElement>(null);
  const bottomScrollRef = useRef<HTMLDivElement>(null);
  // 同步滚动逻辑抽到 useSyncScroll hook, 组件内只负责 ref + handler 绑定
  // (核心 17 行 + 防循环 latch + rAF 防抖, 详见 hooks/useSyncScroll.ts)
  const { onScrollA: onTopScroll, onScrollB: onBottomScroll } = useSyncScroll(
    topScrollRef,
    bottomScrollRef,
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  // single 模式: 单表格(支持 editable / onUpdate), 配 outer Card title
  if (isSingle) {
    const { policies, editable = false, title } = props as SingleProps;
    return (
      <div className="border rounded-lg overflow-hidden">
        {title && (
          <div className="bg-primary/10 px-4 py-2 border-b">
            <h3 className="text-sm font-medium">{title}</h3>
          </div>
        )}
        <div
          ref={bottomScrollRef}
          className="overflow-x-auto"
          onScroll={onBottomScroll}
        >
          <EditableTable policies={policies} onUpdate={onUpdate} editable={editable} />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 上方只读表格 */}
      <div className="border rounded-lg overflow-hidden">
        <div className="bg-muted/50 px-4 py-2 border-b">
          <h3 className="text-sm font-medium">第一次格式化（只读）</h3>
        </div>
        <div
          ref={topScrollRef}
          className="overflow-x-auto"
          onScroll={onTopScroll}
        >
          <table className="w-full border-collapse table-fixed">
            <thead>
              <tr className="border-b bg-muted/30">
                {COLUMNS.map(col => (
                  <th
                    key={col.key}
                    className="px-3 py-2 text-left text-xs font-medium"
                    style={{ width: col.width, minWidth: col.width, maxWidth: col.width }}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {props.topPolicies.map((policy, idx) => (
                <tr key={idx} className="border-b hover:bg-muted/20">
                  {COLUMNS.map(col => {
                    const value = (policy as any)[col.key] || '';
                    return (
                      <td
                        key={col.key}
                        className="px-3 py-2 text-xs align-top"
                        style={{ width: col.width, minWidth: col.width }}
                      >
                        <div className="break-words whitespace-pre-wrap">
                          {value || '\u00A0'}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 下方可编辑表格 */}
      <div className="border rounded-lg overflow-hidden">
        <div className="bg-primary/10 px-4 py-2 border-b">
          <h3 className="text-sm font-medium">第二次格式化（可编辑）</h3>
        </div>
        <div
          ref={bottomScrollRef}
          className="overflow-x-auto"
          onScroll={onBottomScroll}
        >
          <EditableTable
            policies={props.bottomPolicies}
            onUpdate={onUpdate}
            editable={true}
          />
        </div>
      </div>
    </div>
  );
};

// 可编辑表格组件
interface EditableTableProps {
  policies: Policy[];
  onUpdate?: (policies: Policy[]) => void;
  editable?: boolean;  // 默认 true; false 时单元格 onClick 短路, 完全只读
}

const EditableTable = ({ policies, onUpdate, editable = true }: EditableTableProps) => {
  const [editedPolicies, setEditedPolicies] = useState<Policy[]>(policies);
  const [editingCell, setEditingCell] = useState<{ rowId: number; field: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setEditedPolicies(policies);
  }, [policies]);

  const handleCellClick = useCallback((rowId: number, field: string) => {
    setEditingCell({ rowId, field });
  }, []);

  const handleCellChange = useCallback((rowId: number, field: string, value: string) => {
    setEditedPolicies(prev =>
      prev.map(p => (p.id === rowId ? { ...p, [field]: value } : p))
    );
  }, []);

  const handleCellBlur = useCallback(() => {
    if (onUpdate && editingCell) {
      onUpdate(editedPolicies);
    }
    setEditingCell(null);
  }, [editedPolicies, onUpdate, editingCell]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent, rowIdx: number, colIdx: number) => {
    const policy = editedPolicies[rowIdx];
    const field = COLUMNS[colIdx].key;

    if (e.key === 'Enter') {
      e.preventDefault();
      handleCellBlur();
      // 移动到下一行同一列
      if (rowIdx < editedPolicies.length - 1) {
        const nextPolicy = editedPolicies[rowIdx + 1];
        setEditingCell({ rowId: nextPolicy.id!, field });
      }
    } else if (e.key === 'Tab') {
      e.preventDefault();
      handleCellBlur();
      // 移动到下一列
      if (colIdx < COLUMNS.length - 1) {
        setEditingCell({ rowId: policy.id!, field: COLUMNS[colIdx + 1].key });
      } else if (rowIdx < editedPolicies.length - 1) {
        // 移动到下一行第一列
        const nextPolicy = editedPolicies[rowIdx + 1];
        setEditingCell({ rowId: nextPolicy.id!, field: COLUMNS[0].key });
      }
    } else if (e.key === 'Escape') {
      setEditingCell(null);
      setEditedPolicies(policies);
    }
  }, [editedPolicies, handleCellBlur, policies]);

  // 自动聚焦输入框（不自动全选）
  useEffect(() => {
    if (editingCell && inputRef.current) {
      inputRef.current.focus();
      // 移除自动全选，让用户可以自由移动光标
    }
  }, [editingCell]);

  return (
    <table className="w-full border-collapse table-fixed">
      <thead>
        <tr className="border-b bg-muted/30">
          {COLUMNS.map(col => (
            <th 
              key={col.key} 
              className="px-3 py-2 text-left text-xs font-medium"
              style={{ width: col.width, minWidth: col.width }}
            >
              {col.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {editedPolicies.map((policy, rowIdx) => (
          <tr key={policy.id} className="border-b hover:bg-muted/20">
            {COLUMNS.map((col, colIdx) => {
              const value = (policy as any)[col.key] || '';
              const isEditing = editingCell?.rowId === policy.id && editingCell?.field === col.key;

              return (
                <td
                  key={col.key}
                  className={`px-3 py-2 align-top ${editable ? 'cursor-text cursor-pointer' : 'cursor-default'}`}
                  style={{ width: col.width, minWidth: col.width }}
                  onClick={editable ? () => handleCellClick(policy.id!, col.key) : undefined}
                >
                  {isEditing ? (
                    <textarea
                      ref={inputRef as any}
                      value={value}
                      onChange={(e) => handleCellChange(policy.id!, col.key, e.target.value)}
                      onBlur={handleCellBlur}
                      onKeyDown={(e) => handleKeyDown(e, rowIdx, colIdx)}
                      className="w-full px-1 py-1 text-xs border border-blue-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                      rows={3}
                    />
                  ) : (
                    <div className="text-xs break-words whitespace-pre-wrap">
                      {value || '\u00A0'}
                    </div>
                  )}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
};
