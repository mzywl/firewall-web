import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Play, RotateCcw, CheckCircle } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { PushProgressBar } from '../components/push/PushProgressBar';
import { PushLogViewer } from '../components/push/PushLogViewer';
import { useOrder, useStartPush, usePushStatus } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';

export const Push = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [isPushing, setIsPushing] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);

  const { data: order } = useOrder(Number(orderId));
  const startPushMutation = useStartPush(Number(orderId));
  const { data: pushStatus, refetch: refetchStatus } = usePushStatus(
    Number(orderId),
    isPushing
  );
  const { logs, progress, status, clearLogs, resetProgress } = useWebSocket(
    isPushing ? Number(orderId) : null
  );

  useEffect(() => {
    if (status?.status === 'completed' || status?.status === 'failed') {
      setIsPushing(false);
      setIsCompleted(true);
      refetchStatus();
    }
  }, [status, refetchStatus]);

  const handleStart = async () => {
    try {
      clearLogs();
      resetProgress();
      setIsCompleted(false);
      await startPushMutation.mutateAsync();
      setIsPushing(true);
    } catch (error) {
      console.error('启动推送失败:', error);
      alert('启动推送失败，请重试');
    }
  };

  const handleReset = () => {
    setIsPushing(false);
    setIsCompleted(false);
    clearLogs();
    resetProgress();
    refetchStatus();
  };

  const currentProgress = progress?.progress || pushStatus?.progress || 0;
  const currentTotal = progress?.total || pushStatus?.total || 0;
  const currentSuccess = progress?.success || pushStatus?.success || 0;
  const currentFailed = progress?.failed || pushStatus?.failed || 0;
  const currentPending = pushStatus?.pending || 0;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate(`/order/${orderId}/edit`)}
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">策略推送</h1>
            <p className="text-muted-foreground mt-1">
              {order?.title} · 工单号: {order?.order_no}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          {!isPushing && !isCompleted && (
            <Button
              onClick={handleStart}
              disabled={startPushMutation.isPending}
            >
              <Play className="mr-2 h-4 w-4" />
              开始推送
            </Button>
          )}
          {isCompleted && (
            <>
              <Button
                variant="outline"
                onClick={handleReset}
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                重新推送
              </Button>
              <Button
                onClick={() => navigate(`/order/${orderId}/edit`)}
              >
                <CheckCircle className="mr-2 h-4 w-4" />
                返回编辑
              </Button>
            </>
          )}
        </div>
      </div>

      {/* 推送说明 */}
      {!isPushing && !isCompleted && (
        <Card>
          <CardHeader>
            <CardTitle>推送说明</CardTitle>
            <CardDescription>
              点击"开始推送"后，系统将自动将策略推送到对应的防火墙设备
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* 进度显示 */}
      {(isPushing || isCompleted) && (
        <>
          <PushProgressBar
            total={currentTotal}
            success={currentSuccess}
            failed={currentFailed}
            pending={currentPending}
            progress={currentProgress}
            isProcessing={isPushing}
          />

          <PushLogViewer logs={logs} />
        </>
      )}

      {/* 完成提示 */}
      {isCompleted && (
        <Card className="border-green-500/50 bg-green-500/5">
          <CardHeader>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              <CardTitle>推送完成</CardTitle>
            </div>
            <CardDescription>
              {status?.status === 'completed'
                ? `成功推送 ${currentSuccess} 条策略${currentFailed > 0 ? `，${currentFailed} 条失败` : ''}`
                : '推送过程中出现错误，请查看日志'}
            </CardDescription>
          </CardHeader>
        </Card>
      )}
    </div>
  );
};
