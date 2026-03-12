import { useEffect, useCallback, useState } from 'react';
import { socketManager } from '../lib/socket';
import type { PushProgress, PushLog, PushStatusUpdate } from '../types';

export const useWebSocket = (orderId: number | null) => {
  const [isConnected, setIsConnected] = useState(false);
  const [progress, setProgress] = useState<PushProgress | null>(null);
  const [logs, setLogs] = useState<PushLog[]>([]);
  const [status, setStatus] = useState<PushStatusUpdate | null>(null);

  useEffect(() => {
    if (!orderId) return;

    // 连接 WebSocket
    socketManager.connect();
    setIsConnected(true);

    // 加入工单房间
    socketManager.joinOrder(orderId);

    // 监听事件
    const handleProgress = (data: PushProgress) => {
      setProgress(data);
    };

    const handleLog = (data: PushLog) => {
      setLogs(prev => [...prev, data]);
    };

    const handleStatus = (data: PushStatusUpdate) => {
      setStatus(data);
    };

    socketManager.on('push_progress', handleProgress);
    socketManager.on('push_log', handleLog);
    socketManager.on('push_status', handleStatus);

    // 清理
    return () => {
      socketManager.off('push_progress', handleProgress);
      socketManager.off('push_log', handleLog);
      socketManager.off('push_status', handleStatus);
      socketManager.leaveOrder(orderId);
    };
  }, [orderId]);

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  const resetProgress = useCallback(() => {
    setProgress(null);
    setStatus(null);
  }, []);

  return {
    isConnected,
    progress,
    logs,
    status,
    clearLogs,
    resetProgress,
  };
};
