import { io, Socket } from 'socket.io-client';
import type { PushProgress, PushLog, PushStatusUpdate } from '../types';

// 同源：空 URL，nginx 同域名反代 /socket.io
// 如需直连后端调试，可设 VITE_SOCKET_URL=http://localhost:18000
const SOCKET_URL = import.meta.env.VITE_SOCKET_URL ?? '';

class SocketManager {
  private socket: Socket | null = null;
  private listeners: Map<string, Set<Function>> = new Map();

  connect() {
    if (this.socket?.connected) return;

    this.socket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
    });

    this.socket.on('connect', () => {
      console.log('WebSocket connected');
    });

    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected');
    });

    this.socket.on('push_progress', (data: PushProgress) => {
      this.emit('push_progress', data);
    });

    this.socket.on('push_log', (data: PushLog) => {
      this.emit('push_log', data);
    });

    this.socket.on('push_status', (data: PushStatusUpdate) => {
      this.emit('push_status', data);
    });
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  joinOrder(orderId: number) {
    if (this.socket?.connected) {
      this.socket.emit('join_order', { order_id: orderId });
    }
  }

  leaveOrder(orderId: number) {
    if (this.socket?.connected) {
      this.socket.emit('leave_order', { order_id: orderId });
    }
  }

  on(event: string, callback: Function) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  off(event: string, callback: Function) {
    const callbacks = this.listeners.get(event);
    if (callbacks) {
      callbacks.delete(callback);
    }
  }

  private emit(event: string, data: any) {
    const callbacks = this.listeners.get(event);
    if (callbacks) {
      callbacks.forEach(callback => callback(data));
    }
  }
}

export const socketManager = new SocketManager();
