"""
WebSocket 服务端
"""
import socketio
from fastapi import FastAPI

# 创建 Socket.IO 服务器
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)

# 创建 ASGI 应用
socket_app = socketio.ASGIApp(sio)


@sio.event
async def connect(sid, environ):
    """客户端连接"""
    print(f"Client connected: {sid}")
    await sio.emit('connected', {'message': 'Connected to server'}, room=sid)


@sio.event
async def disconnect(sid):
    """客户端断开"""
    print(f"Client disconnected: {sid}")


@sio.event
async def join_order(sid, data):
    """加入工单房间"""
    order_id = data.get('order_id')
    if order_id:
        room = f"order_{order_id}"
        await sio.enter_room(sid, room)
        print(f"Client {sid} joined room {room}")
        await sio.emit('joined', {'order_id': order_id}, room=sid)


@sio.event
async def leave_order(sid, data):
    """离开工单房间"""
    order_id = data.get('order_id')
    if order_id:
        room = f"order_{order_id}"
        await sio.leave_room(sid, room)
        print(f"Client {sid} left room {room}")


async def broadcast_push_progress(order_id: int, progress: dict):
    """广播推送进度"""
    room = f"order_{order_id}"
    await sio.emit('push_progress', progress, room=room)


async def broadcast_push_log(order_id: int, log: dict):
    """广播推送日志"""
    room = f"order_{order_id}"
    await sio.emit('push_log', log, room=room)


async def broadcast_push_status(order_id: int, status: dict):
    """广播推送状态变更"""
    room = f"order_{order_id}"
    await sio.emit('push_status', status, room=room)


def mount_socketio(app: FastAPI):
    """挂载 Socket.IO 到 FastAPI"""
    app.mount('/socket.io', socket_app)
    return sio
