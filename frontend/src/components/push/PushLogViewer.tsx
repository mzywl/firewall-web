import { useEffect, useRef } from 'react';
import { CheckCircle2, XCircle, Info, AlertTriangle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';

// 通用日志条目（兼容 v1 WebSocket 和 v2 DB log）
export interface GenericPushLog {
  id?: number;
  seq?: number;
  level: 'info' | 'success' | 'error' | 'warning';
  message: string;
  stage?: string;
  timestamp?: number | string;
}

interface PushLogViewerProps {
  logs: GenericPushLog[];
  emptyText?: string;
}

export const PushLogViewer = ({ logs, emptyText = '暂无日志' }: PushLogViewerProps) => {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const getIcon = (level: string) => {
    switch (level) {
      case 'success':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case 'error':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'warning':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      default:
        return <Info className="h-4 w-4 text-blue-500" />;
    }
  };

  const getTextColor = (level: string) => {
    switch (level) {
      case 'success':
        return 'text-green-600 dark:text-green-400';
      case 'error':
        return 'text-red-600 dark:text-red-400';
      case 'warning':
        return 'text-yellow-600 dark:text-yellow-400';
      default:
        return 'text-blue-600 dark:text-blue-400';
    }
  };

  const formatTime = (ts: number | string | undefined) => {
    if (!ts) return '';
    const d = typeof ts === 'number' && ts < 1e12 ? new Date(ts * 1000) : new Date(ts);
    return d.toLocaleTimeString('zh-CN');
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>推送日志</CardTitle>
          {logs.length > 0 && (
            <span className="text-xs text-muted-foreground">{logs.length} 条</span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="bg-muted/30 rounded-lg p-4 max-h-[500px] overflow-y-auto font-mono text-sm">
          {logs.length === 0 ? (
            <div className="text-muted-foreground text-center py-8">{emptyText}</div>
          ) : (
            <div className="space-y-2">
              {logs.map((log, index) => (
                <div key={log.id ?? `idx-${index}`} className="flex items-start gap-2">
                  <span className="text-muted-foreground text-xs mt-0.5 flex-shrink-0">
                    {formatTime(log.timestamp)}
                  </span>
                  {log.seq !== undefined && (
                    <span className="text-muted-foreground text-xs mt-0.5 flex-shrink-0 min-w-[3ch] text-right">
                      #{log.seq}
                    </span>
                  )}
                  {log.stage && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground flex-shrink-0">
                      {log.stage}
                    </span>
                  )}
                  {getIcon(log.level)}
                  <span className={`${getTextColor(log.level)} break-all`}>{log.message}</span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};
