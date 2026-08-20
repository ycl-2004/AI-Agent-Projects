"""
OTA Frontend Server — Starlette + SSE 实时推送层。

==============================================================================
运行方式 (在能运行 OTA 的环境, 例如):
    conda activate LC
    python frontend/server.py
    -> 浏览器打开 http://127.0.0.1:8789

架构说明:
  - 复用 pipeline.py 的 process_single_ticket / stream_ticket_reply, 不改动后端;
  - stdout 线程分流捕获: 工作线程里 pipeline 的 print 被解析为结构化事件,
    CLI (python main.py) 行为完全不变;
  - 单工单 = 1 个后台线程; 批处理 = 服务端 ThreadPoolExecutor (每单独立线程,
    事件带工单序号); 流式 = 后台线程逐 chunk 推送打字机效果;
  - 浏览器通过 GET /api/events/{sid} (SSE) 实时接收事件, 支持 Last-Event-ID
    断线重连回放, 刷新页面即可完整重建界面状态。
==============================================================================
"""

import re
import sys
import os
import time
import uuid
import json
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from pipeline import process_single_ticket, stream_ticket_reply

FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = "127.0.0.1"
PORT = 8789


# ----------------------------------------------------
# stdout 线程分流: 注册了 sink 的工作线程 print -> 事件, 其余透传终端
# ----------------------------------------------------
_tls = threading.local()


class _DispatchStdout:
    def __init__(self, default):
        self._default = default

    def write(self, s):
        sink = getattr(_tls, "sink", None)
        if sink is not None:
            if s:
                sink(s)
        else:
            self._default.write(s)

    def flush(self):
        self._default.flush()

    def __getattr__(self, name):
        return getattr(self._default, name)


sys.stdout = _DispatchStdout(sys.stdout)


# ----------------------------------------------------
# pipeline 输出解析: 把 print 行映射为结构化事件
# ----------------------------------------------------
_PATTERNS = [
    (re.compile(r"\[Step 1\]"), "step1"),
    (re.compile(r"模型决策：识别到需要调用 (\d+) 个工具"), "decision"),
    (re.compile(r"\[执行工具\] 名称: (\S+) \| 参数: (.+) \| ID: \S+"), "tool_call"),
    (re.compile(r"\[工具产出\] -> (.*)"), "tool_out"),
    (re.compile(r"无需调用外部工具"), "no_tool"),
    (re.compile(r"\[Step 2\] 正在抽取强类型质检报告 \(Attempt (\d+)\)"), "step2"),
    (re.compile(r"TicketResolution Pydantic 校验通过"), "validated"),
    (re.compile(r"触发服务商频控保护"), "ratelimit"),
    (re.compile(r"结构化校验失败"), "invalid"),
]


_IGNORE = re.compile(r"For troubleshooting, visit|Troubleshoot this error")

class PipelineWatcher:
    """线程内捕获 pipeline stdout, 按行解析后推入 session 事件流。"""

    def __init__(self, session, ticket_index=None):
        self.session = session
        self.ticket_index = ticket_index
        self._buf = ""

    def write(self, raw):
        self._buf += raw
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._handle(line)

    def _push(self, event):
        if self.ticket_index is not None:
            event["ticket"] = self.ticket_index
        self.session.push(event)

    def _handle(self, line):
        text = line.strip()
        if not text:
            return
        if _IGNORE.search(text):
            return
        for pattern, kind in _PATTERNS:
            m = pattern.search(text)
            if not m:
                continue
            if kind == "step1":
                self._push({"type": "stage", "key": "prep", "state": "done"})
                self._push({"type": "stage", "key": "intent", "state": "active"})
            elif kind == "decision":
                self._push({"type": "log", "level": "info", "text": f"模型决策调用 {m.group(1)} 个工具"})
                self._push({"type": "stage", "key": "tools", "state": "active"})
            elif kind == "tool_call":
                self._push({"type": "tool", "name": m.group(1), "args": m.group(2)})
            elif kind == "tool_out":
                self._push({"type": "tool_output", "output": m.group(1)})
            elif kind == "no_tool":
                self._push({"type": "log", "level": "info", "text": "模型判断无需调用外部工具"})
                self._push({"type": "stage", "key": "tools", "state": "done"})
            elif kind == "step2":
                self._push({"type": "stage", "key": "intent", "state": "done"})
                self._push({"type": "stage", "key": "tools", "state": "done"})
                self._push({"type": "stage", "key": "extract", "state": "active"})
                self._push({"type": "attempt", "n": int(m.group(1))})
            elif kind == "validated":
                self._push({"type": "validated"})
                self._push({"type": "stage", "key": "extract", "state": "done"})
            elif kind == "ratelimit":
                self._push({"type": "log", "level": "warn", "text": "触发服务商频控保护 (429), 退避重试中"})
            elif kind == "invalid":
                self._push({"type": "log", "level": "warn", "text": "结构化校验失败, 注入错误自愈重试"})
            return
        self._push({"type": "log", "level": "info", "text": text})


def _run_with_watcher(session, fn, ticket_index=None):
    watcher = PipelineWatcher(session, ticket_index)
    _tls.sink = watcher.write
    try:
        return fn()
    finally:
        _tls.sink = None


# ----------------------------------------------------
# Session 管理 (事件日志 + 条件变量, 支持 SSE 回放)
# ----------------------------------------------------
class Session:
    def __init__(self, mode: str):
        self.id = uuid.uuid4().hex[:12]
        self.mode = mode
        self.events = []
        self.cond = threading.Condition()
        self.status = "running"
        self.created_at = time.time()

    def push(self, event):
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()


SESSIONS: dict[str, Session] = {}


# ----------------------------------------------------
# 后台工作线程: 三种模式
# ----------------------------------------------------
def run_single(session: Session, ticket: dict):
    session.push({"type": "start", "data": {"mode": "single", "ticket": ticket}})
    session.push({"type": "stage", "key": "prep", "state": "active"})
    t0 = time.time()
    try:
        res = _run_with_watcher(session, lambda: process_single_ticket(ticket))
        session.push({"type": "stage", "key": "report", "state": "done"})
        session.push({"type": "result", "data": {
            "resolution": res.model_dump(),
            "elapsed": round(time.time() - t0, 2),
        }})
        session.status = "finished"
        session.push({"type": "done", "data": {"status": "finished", "elapsed": round(time.time() - t0, 2)}})
    except Exception as e:
        session.status = "error"
        session.push({"type": "error", "data": {"message": f"{type(e).__name__}: {e}"}})
    finally:
        session.push({"type": "end", "data": {"status": session.status}})


def run_batch(session: Session, tickets: list[dict]):
    session.push({"type": "start", "data": {"mode": "batch", "tickets": tickets}})
    t0 = time.time()

    def worker(index: int, ticket: dict):
        session.push({"type": "stage", "key": "prep", "state": "active", "ticket": index})
        try:
            res = _run_with_watcher(
                session, lambda: process_single_ticket(ticket), ticket_index=index
            )
            session.push({"type": "batch_result", "ticket": index, "data": {"resolution": res.model_dump()}})
        except Exception as e:
            session.push({"type": "batch_error", "ticket": index, "data": {"message": f"{type(e).__name__}: {e}"}})

    with ThreadPoolExecutor(max_workers=min(len(tickets), 5)) as pool:
        futures = [pool.submit(worker, i, t) for i, t in enumerate(tickets)]
        for f in futures:
            f.result()

    session.status = "finished"
    session.push({"type": "done", "data": {"status": "finished", "elapsed": round(time.time() - t0, 2)}})
    session.push({"type": "end", "data": {"status": session.status}})


def run_stream(session: Session, ticket: dict):
    session.push({"type": "start", "data": {"mode": "stream", "ticket": ticket}})
    session.push({"type": "stage", "key": "reply", "state": "active"})
    t0 = time.time()
    try:
        for chunk in stream_ticket_reply(ticket):
            session.push({"type": "chunk", "data": {"text": chunk}})
        session.status = "finished"
        session.push({"type": "done", "data": {"status": "finished", "elapsed": round(time.time() - t0, 2)}})
    except Exception as e:
        session.status = "error"
        session.push({"type": "error", "data": {"message": f"{type(e).__name__}: {e}"}})
    finally:
        session.push({"type": "end", "data": {"status": session.status}})


# ----------------------------------------------------
# 输入校验
# ----------------------------------------------------
def _num(value, default, cast=float):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def _clean_ticket(raw: dict, minimal: bool = False) -> dict:
    raw = raw or {}
    ticket_text = str(raw.get("ticket_text", "")).strip()
    if not ticket_text:
        raise ValueError("ticket_text required")
    if len(ticket_text) > 1000:
        raise ValueError("ticket_text too long")

    ticket = {
        "ticket_text": ticket_text,
        "user_id": str(raw.get("user_id", "")).strip() or "guest",
    }
    if minimal:
        return ticket
    order_amount = _num(raw.get("order_amount"), 0.0)
    delay_hours = int(_num(raw.get("delay_hours"), 0, cast=int))
    ticket.update({
        "order_id": str(raw.get("order_id", "")).strip() or None,
        "order_amount": max(order_amount, 0.0),
        "delay_hours": max(delay_hours, 0),
    })
    return ticket


# ----------------------------------------------------
# HTTP Handlers
# ----------------------------------------------------
async def start(request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    mode = str(body.get("mode", "")).strip()

    try:
        if mode == "single":
            ticket = _clean_ticket(body.get("ticket"))
            session = Session(mode)
            SESSIONS[session.id] = session
            threading.Thread(target=run_single, args=(session, ticket), daemon=True).start()

        elif mode == "batch":
            tickets_raw = body.get("tickets") or []
            if not isinstance(tickets_raw, list) or not (1 <= len(tickets_raw) <= 5):
                return JSONResponse({"error": "tickets must be a list of 1~5"}, status_code=400)
            tickets = [_clean_ticket(t) for t in tickets_raw]
            session = Session(mode)
            SESSIONS[session.id] = session
            threading.Thread(target=run_batch, args=(session, tickets), daemon=True).start()

        elif mode == "stream":
            ticket = _clean_ticket(body.get("ticket"), minimal=True)
            session = Session(mode)
            SESSIONS[session.id] = session
            threading.Thread(target=run_stream, args=(session, ticket), daemon=True).start()

        else:
            return JSONResponse({"error": "mode must be single | batch | stream"}, status_code=400)

    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    return JSONResponse({
        "session_id": session.id,
        "mode": mode,
        "events_url": f"/api/events/{session.id}",
    })


def _wait_for_events(session: Session, cursor: int, timeout: float):
    with session.cond:
        if len(session.events) <= cursor:
            session.cond.wait(timeout)


async def stream_events(request):
    sid = request.path_params["sid"]
    session = SESSIONS.get(sid)
    if session is None:
        return JSONResponse({"error": "session not found"}, status_code=404)

    async def event_stream():
        try:
            cursor = int(request.headers.get("last-event-id", "0"))
        except ValueError:
            cursor = 0

        while True:
            if await request.is_disconnected():
                break

            while cursor < len(session.events):
                event = session.events[cursor]
                cursor += 1
                payload = json.dumps(event, ensure_ascii=False)
                yield f"id: {cursor}\ndata: {payload}\n\n"

            if session.status in ("finished", "error") and cursor >= len(session.events):
                yield "event: eos\ndata: {}\n\n"
                break

            await asyncio.to_thread(_wait_for_events, session, cursor, 15)
            yield ": ping\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def index(request):
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


async def health(request):
    return JSONResponse({"ok": True, "sessions": len(SESSIONS)})


# ----------------------------------------------------
# App 装配
# ----------------------------------------------------
routes = [
    Route("/", index),
    Route("/api/health", health),
    Route("/api/start", start, methods=["POST"]),
    Route("/api/events/{sid}", stream_events),
    Mount("/static", app=StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static"),
]

app = Starlette(routes=routes)


if __name__ == "__main__":
    print("=" * 60)
    print("  OTA Frontend Server")
    print(f"  ->  http://{HOST}:{PORT}")
    print("=" * 60)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
