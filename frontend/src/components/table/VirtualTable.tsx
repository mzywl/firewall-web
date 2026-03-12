import { useState, useCallback, useEffect, useRef } from 'react';
import type { Policy } from '../../types';

interface VirtualTableProps {
  policies: Policy[];
  onUpdate?: (policies: Policy[]) => void;
  editable?: boolean;
  loading?: boolean;
}

const SYSTEM_FIELDS = ['id', 'order_id', 'firewall_id', 'is_merged', 'push_status', 'created_at', 'action'];
const COLUMN_WIDTH = 150;
const HEADER_HEIGHT = 40;

export const VirtualTable = ({
  policies,
  onUpdate,
  editable = false,
  loading = false
}: VirtualTableProps) => {
  const [editedPolicies, setEditedPolicies] = useState<Policy[]>(policies);
  const [editingCell, setEditingCell] = useState<{ rowIdx: number; colIdx: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const columns = policies.length > 0
    ? Object.keys(policies[0]).filter(key => !SYSTEM_FIELDS.includes(key))
    : [];

  useEffect(() => {
    setEditedPolicies(policies);
  }, [policies]);

  const handleCellClick = useCallback((rowIdx: number, colIdx: number) => {
    if (editable) {
      setEditingCell({ rowIdx, colIdx });
    }
  }, [editable]);

  const handleCellChange = useCallback((rowIdx: number, colIdx: number, value: string) => {
    const field = columns[colIdx];
    setEditedPolicies(prev =>
      prev.map((p, idx) => (idx === rowIdx ? { ...p, [field]: value } : p))
    );
  }, [columns]);

  const handleCellBlur = useCallback(() => {
    if (onUpdate && editingCell) {
      onUpdate(editedPolicies);
    }
    setEditingCell(null);
  }, [editedPolicies, onUpdate, editingCell]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (policies.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        暂无策略数据
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-full">
      {/* 表头 */}
      <div className="flex border-b bg-muted/50" style={{ height: HEADER_HEIGHT }}>
        {columns.map((col) => (
          <div
            key={col}
            className="border-r px-2 flex items-center text-xs font-medium"
            style={{ width: COLUMN_WIDTH, minWidth: COLUMN_WIDTH }}
          >
            {col}
          </div>
        ))}
      </div>

      {/* 简化版表格（暂不使用虚拟滚动，避免依赖问题） */}
      <div className="overflow-auto" style={{ maxHeight: 600 }}>
        <table className="w-full border-collapse">
          <tbody>
            {editedPolicies.map((policy, rowIdx) => (
              <tr key={policy.id} className="border-b hover:bg-muted/20">
                {columns.map((col, colIdx) => {
                  const value = (policy as any)[col] || '';
                  const isEditing = editingCell?.rowIdx === rowIdx && editingCell?.colIdx === colIdx;

                  return (
                    <td
                      key={col}
                      className="px-2 py-2 cursor-text border-r"
                      style={{ width: COLUMN_WIDTH, minWidth: COLUMN_WIDTH }}
                      onClick={() => handleCellClick(rowIdx, colIdx)}
                    >
                      {isEditing ? (
                        <input
                          type="text"
                          value={value}
                          onChange={(e) => handleCellChange(rowIdx, colIdx, e.target.value)}
                          onBlur={handleCellBlur}
                          autoFocus
                          className="w-full px-1 py-1 text-xs border border-blue-500 rounded"
                        />
                      ) : (
                        <span className="text-xs truncate block" title={value}>
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
      </div>
    </div>
  );
};
