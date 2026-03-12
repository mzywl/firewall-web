import { useRef, useEffect, useCallback } from 'react';
import type { Policy } from '../../types';

interface SyncScrollTableProps {
  topPolicies: Policy[];
  bottomPolicies: Policy[];
  onUpdate?: (policies: Policy[]) => void;
  loading?: boolean;
}

// 系统字段，不显示在表格中
const SYSTEM_FIELDS = ['id', 'order_id', 'firewall_id', 'is_merged', 'push_status', 'created_at', 'action'];

export const SyncScrollTable = ({
  topPolicies,
  bottomPolicies,
  onUpdate,
  loading = false
}: SyncScrollTableProps) => {
  const topScrollRef = useRef<HTMLDivElement>(null);
  const bottomScrollRef = useRef<HTMLDivElement>(null);
  const isScrollingRef = useRef(false);

  // 动态获取表格列（排除系统字段）
  const columns = topPolicies.length > 0 
    ? Object.keys(topPolicies[0]).filter(key => !SYSTEM_FIELDS.includes(key))
    : [];

  // 同步滚动处理（使用 requestAnimationFrame 防抖）
  const handleScroll = useCallback((source: 'top' | 'bottom') => {
    if (isScrollingRef.current) return;

    const sourceRef = source === 'top' ? topScrollRef : bottomScrollRef;
    const targetRef = source === 'top' ? bottomScrollRef : topScrollRef;

    if (!sourceRef.current || !targetRef.current) return;

    isScrollingRef.current = true;

    requestAnimationFrame(() => {
      if (targetRef.current && sourceRef.current) {
        targetRef.current.scrollLeft = sourceRef.current.scrollLeft;
      }
      isScrollingRef.current = false;
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
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
          onScroll={() => handleScroll('top')}
        >
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b bg-muted/30">
                {columns.map(col => (
                  <th key={col} className="px-3 py-2 text-left text-xs font-medium whitespace-nowrap min-w-[120px]">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {topPolicies.map((policy, idx) => (
                <tr key={idx} className="border-b hover:bg-muted/20">
                  {columns.map(col => {
                    const value = (policy as any)[col] || '';
                    return (
                      <td key={col} className="px-3 py-2 text-xs whitespace-nowrap min-w-[120px]">
                        <span className="block truncate max-w-xs" title={value}>
                          {value || '\u00A0'}
                        </span>
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
          onScroll={() => handleScroll('bottom')}
        >
          <EditableTable
            policies={bottomPolicies}
            columns={columns}
            onUpdate={onUpdate}
          />
        </div>
      </div>
    </div>
  );
};

// 可编辑表格组件
interface EditableTableProps {
  policies: Policy[];
  columns: string[];
  onUpdate?: (policies: Policy[]) => void;
}

const EditableTable = ({ policies, columns, onUpdate }: EditableTableProps) => {
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
    const field = columns[colIdx];

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
      if (colIdx < columns.length - 1) {
        setEditingCell({ rowId: policy.id!, field: columns[colIdx + 1] });
      } else if (rowIdx < editedPolicies.length - 1) {
        // 移动到下一行第一列
        const nextPolicy = editedPolicies[rowIdx + 1];
        setEditingCell({ rowId: nextPolicy.id!, field: columns[0] });
      }
    } else if (e.key === 'Escape') {
      setEditingCell(null);
      setEditedPolicies(policies);
    }
  }, [editedPolicies, columns, handleCellBlur, policies]);

  // 自动聚焦输入框
  useEffect(() => {
    if (editingCell && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingCell]);

  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b bg-muted/30">
          {columns.map(col => (
            <th key={col} className="px-3 py-2 text-left text-xs font-medium whitespace-nowrap min-w-[120px]">
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {editedPolicies.map((policy, rowIdx) => (
          <tr key={policy.id} className="border-b hover:bg-muted/20">
            {columns.map((col, colIdx) => {
              const value = (policy as any)[col] || '';
              const isEditing = editingCell?.rowId === policy.id && editingCell?.field === col;

              return (
                <td
                  key={col}
                  className="px-3 py-2 cursor-text whitespace-nowrap min-w-[120px]"
                  onClick={() => handleCellClick(policy.id!, col)}
                >
                  {isEditing ? (
                    <input
                      ref={inputRef}
                      type="text"
                      value={value}
                      onChange={(e) => handleCellChange(policy.id!, col, e.target.value)}
                      onBlur={handleCellBlur}
                      onKeyDown={(e) => handleKeyDown(e, rowIdx, colIdx)}
                      className="w-full px-1 py-1 text-xs border border-blue-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  ) : (
                    <span className="block truncate max-w-xs text-xs" title={value}>
                      {value || '\u00A0'}
                    </span>
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

// 导入 useState
import { useState } from 'react';
