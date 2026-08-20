"""
Lightweight Progress Event Bus for DRS.

==============================================================================
作用：
  - CLI 运行 (python main.py)：行为与原来完全一致，emit() 默认同步打印 message；
  - Web 运行 (frontend/server.py)：工作线程可注册自己的 sink，把结构化事件
    实时推送给浏览器 (SSE)，同时终端依然保留原始输出。

事件结构 (dict):
  {
    "type":    "stage" | "tool" | "note" | "eval" | "route" | "review_required"
               | "chunk" | "done" | "error" | "end",
    "stage":   "planner" | "research" | "evaluator" | "reviewer" | "writer"
               | "exporter" | None,
    "status":  "start" | "done" | ...  (可选),
    "message": 人类可读的终端日志文本 (可选),
    "data":    结构化载荷 (可选),
  }

quiet=True 的事件不打印终端 (如 writer 逐 token 流式块)。
线程路由：sink 只接收「注册它的线程」发出的事件，避免多会话串流。
==============================================================================
"""

import threading
import time

_lock = threading.Lock()
_sinks = []  # [(owner_thread_ident, callable)]


def add_sink(fn) -> None:
    """注册当前线程的事件 sink (仅接收本线程内 emit 的事件)。"""
    with _lock:
        _sinks.append((threading.get_ident(), fn))


def remove_sink(fn) -> None:
    with _lock:
        _sinks[:] = [(owner, f) for owner, f in _sinks if f is not fn]


def emit(event: dict, quiet: bool = False) -> None:
    """
    发布一条进度事件：
    1. 广播给匹配的 sink (前端 SSE)；
    2. 非 quiet 事件照常打印 message 到终端，保持 CLI 体验不变。
    """
    event = {"ts": round(time.time(), 3), **event}
    current = threading.get_ident()

    with _lock:
        matched = [fn for owner, fn in _sinks if owner == current]

    for fn in matched:
        try:
            fn(event)
        except Exception:
            pass

    if not quiet:
        message = event.get("message")
        if message:
            print(message, flush=True)
