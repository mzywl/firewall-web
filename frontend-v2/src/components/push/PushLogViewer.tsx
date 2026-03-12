import { useEffect, useRef } from 'react';
import { CheckCircle2, XCircle, Info, AlertTriangle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import type { PushLog } from '../../types';

interface PushLogViewerProps {
  logs: PushLog[];
}

export const PushLogViewer = ({ logs }: PushLogViewerProps) => {
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>推送日志</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="bg-muted/30 rounded-lg p-4 max-h-96 overflow-y-auto font-mono text-sm">
          {logs.length === 0 ? (
            <div className="text-muted-foreground text-center py-8">
              暂无日志
            </div>
          ) : (
            <div className="space-y-2">
              {logs.map((log, index) => (
                <div key={index} className="flex items-start gap-2">
                  <span className="text-muted-foreground text-xs mt-0.5">
                    {new Date(log.timestamp).toLocaleTimeString('zh-CN')}
                  </span>
                  {getIcon(log.level)}
                  <span className={getTextColor(log.level)}>
                    {log.message}
                  </span>
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
