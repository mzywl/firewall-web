import { useState, useCallback, useMemo, useEffect } from 'react';
import type { Policy } from '../../types';

interface PolicyTableProps {
  policies: Policy[];
  onUpdate?: (policies: Policy[]) => void;
  editable?: boolean;
  loading?: boolean;
}

// 系统字段，不显示在表格中
const SYSTEM_FIELDS = ['id', 'order_id', 'firewall_id', 'is_merged', 'push_status', 'created_at', 'action'];

export const PolicyTable = ({ 
  policies, 
  onUpdate, 
  editable = false,
  loading = false 
}: PolicyTableProps) => {
  const [editedPolicies, setEditedPolicies] = useState<Policy[]>(policies);
  const [editingCell, setEditingCell] = useState<{ rowId: number; field: string } | null>(null);

  // 同步外部数据变化
  useEffect(() => {
    setEditedPolicies(policies);
  }, [policies]);

  // 动态获取表格列（排除系统字段）
  const columns = useMemo(() => {
    if (policies.length === 0) return [];
    
    const firstPolicy = policies[0];
    return Object.keys(firstPolicy).filter(key => !SYSTEM_FIELDS.includes(key));
  }, [policies]);

  const handleCellClick = useCallback((rowId: number, field: string) => {
    if (editable) {
      setEditingCell({ rowId, field });
    }
  }, [editable]);

  const handleCellChange = useCallback((rowId: number, field: string, value: string) => {
    setEditedPolicies(prev =>
      prev.map(p => (p.id === rowId ? { ...p, [field]: value } : p))
    );
  }, []);

  const handleCellBlur = useCallback(() => {
    // 失去焦点时自动保存
    if (onUpdate && editingCell) {
      onUpdate(editedPolicies);
    }
    setEditingCell(null);
  }, [editedPolicies, onUpdate, editingCell]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleCellBlur();
    } else if (e.key === 'Escape') {
      setEditingCell(null);
      setEditedPolicies(policies);
    }
  }, [handleCellBlur, policies]);

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
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b bg-muted/50">
            {columns.map(col => (
              <th key={col} className="px-2 py-3 text-left text-sm font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {editedPolicies.map((policy) => {
            return (
              <tr key={policy.id} className="border-b hover:bg-muted/30 transition-colors">
                {columns.map(col => {
                  const value = (policy as any)[col] || '';
                  const isEditing = editingCell?.rowId === policy.id && editingCell?.field === col;
                  
                  return (
                    <td 
                      key={col} 
                      className={`px-2 py-2 ${editable ? 'cursor-text' : ''}`}
                      onClick={() => handleCellClick(policy.id!, col)}
                    >
                      {isEditing ? (
                        <input
                          type="text"
                          value={value}
                          onChange={(e) => handleCellChange(policy.id!, col, e.target.value)}
                          onBlur={handleCellBlur}
                          onKeyDown={handleKeyDown}
                          autoFocus
                          className="w-full px-1 py-1 text-xs border border-blue-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                      ) : (
                        <span 
                          className="text-xs block truncate max-w-xs" 
                          title={value}
                        >
                          {value || '\u00A0'}
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
