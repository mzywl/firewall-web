import { Progress } from '../ui/Progress';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { CheckCircle2, XCircle, Clock, Loader2 } from 'lucide-react';

interface PushProgressProps {
  total: number;
  success: number;
  failed: number;
  pending: number;
  progress: number;
  isProcessing: boolean;
}

export const PushProgressBar = ({
  total,
  success,
  failed,
  pending,
  progress,
  isProcessing,
}: PushProgressProps) => {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>推送进度</CardTitle>
          {isProcessing && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              推送中...
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* 进度条 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">总体进度</span>
            <span className="font-semibold">{progress}%</span>
          </div>
          <Progress value={progress} max={100} />
        </div>

        {/* 统计信息 */}
        <div className="grid grid-cols-4 gap-4">
          <div className="text-center p-4 bg-muted/30 rounded-lg">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Clock className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="text-2xl font-bold">{total}</div>
            <div className="text-xs text-muted-foreground mt-1">总计</div>
          </div>

          <div className="text-center p-4 bg-green-500/10 rounded-lg">
            <div className="flex items-center justify-center gap-2 mb-2">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
            </div>
            <div className="text-2xl font-bold text-green-600 dark:text-green-400">
              {success}
            </div>
            <div className="text-xs text-muted-foreground mt-1">成功</div>
          </div>

          <div className="text-center p-4 bg-red-500/10 rounded-lg">
            <div className="flex items-center justify-center gap-2 mb-2">
              <XCircle className="h-5 w-5 text-red-500" />
            </div>
            <div className="text-2xl font-bold text-red-600 dark:text-red-400">
              {failed}
            </div>
            <div className="text-xs text-muted-foreground mt-1">失败</div>
          </div>

          <div className="text-center p-4 bg-blue-500/10 rounded-lg">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Clock className="h-5 w-5 text-blue-500" />
            </div>
            <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {pending}
            </div>
            <div className="text-xs text-muted-foreground mt-1">待推送</div>
          </div>
        </div>

        {/* 成功率 */}
        {total > 0 && (
          <div className="text-center pt-4 border-t">
            <div className="text-sm text-muted-foreground">成功率</div>
            <div className="text-3xl font-bold mt-2">
              {((success / total) * 100).toFixed(1)}%
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
