"""
DRS Frontend Server — Starlette + SSE 实时推送层。

==============================================================================
运行方式 (在项目根目录):
    conda activate LC
    python frontend/server.py
    -> 浏览器打开 http://localhost:8788

架构说明:
  - 复用 graph.py 编译出的同一个 LangGraph 应用 (含 MemorySaver)；
  - 每次调研 = 一个 Session (后台线程跑 app.invoke，事件经 progress 总线入队)；
  - 浏览器通过 GET /api/events/{sid} (SSE) 实时接收事件，支持断线重连回放；
  - HITL: app.invoke 命中 interrupt() 挂起后，前端 POST /api/review
    以 Command(resume=...) 唤醒同一 thread 继续流转。
==============================================================================
"""

import asyncio
import json
import os
import sys
import threading
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

import progress
from state import initial_state
from graph import app as graph_app
from langgraph.types import Command

FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = "127.0.0.1"
PORT = 8788


# ----------------------------------------------------
# Session 管理 (事件日志 + 条件变量，支持 SSE 回放)
# ----------------------------------------------------
class Session:
    def __init__(self, topic: str):
        self.id = uuid.uuid4().hex[:12]
        self.topic = topic
        self.thread_id = f"research-session-{self.id}"
        self.config = {"configurable": {"thread_id": self.thread_id}}
        self.events = []                # 完整事件日志 (回放用)
        self.cond = threading.Condition()
        self.status = "running"         # running | awaiting_review | finished | error
        self.created_at = time.time()
        self.review_round = 0           # 大纲送审次数 (修订回路会有多轮)

    def push(self, event: dict):
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()


SESSIONS: dict[str, Session] = {}


# ----------------------------------------------------
# 后台工作线程：运行 LangGraph，把 progress 事件路由进 Session
# ----------------------------------------------------
def _sink_for(session: Session):
    def sink(event: dict):
        session.push(event)
    return sink


def run_session(session: Session, resume_feedback: str | None = None):
    sink = _sink_for(session)
    progress.add_sink(sink)
    try:
        if resume_feedback is None:
            result = graph_app.invoke(initial_state(session.topic), config=session.config)
        else:
            result = graph_app.invoke(Command(resume=resume_feedback), config=session.config)

        if "__interrupt__" in result:
            snapshot = graph_app.get_state(session.config)
            values = snapshot.values or {}
            session.review_round += 1
            session.status = "awaiting_review"
            session.push({
                "type": "review_required",
                "data": {
                    "topic": values.get("topic", session.topic),
                    "outline": values.get("outline", ""),
                    "notes_count": len(values.get("research_notes", [])),
                    "round": session.review_round,
                },
            })
        else:
            session.status = "finished"
            session.push({
                "type": "done",
                "data": {
                    "topic": result.get("topic", session.topic),
                    "report": result.get("report_content", ""),
                    "filepath": result.get("output_filepath", ""),
                    "notes_count": len(result.get("research_notes", [])),
                },
            })
    except Exception as e:
        session.status = "error"
        session.push({"type": "error", "data": {"message": f"{type(e).__name__}: {e}"}})
    finally:
        progress.remove_sink(sink)
        session.push({"type": "end", "data": {"status": session.status}})


# ----------------------------------------------------
# HTTP Handlers
# ----------------------------------------------------
async def start_research(request):
    body = await request.json()
    topic = str(body.get("topic", "")).strip()
    if not topic:
        return JSONResponse({"error": "topic required"}, status_code=400)
    if len(topic) > 200:
        return JSONResponse({"error": "topic too long"}, status_code=400)

    session = Session(topic)
    SESSIONS[session.id] = session
    threading.Thread(target=run_session, args=(session,), daemon=True).start()

    return JSONResponse({
        "session_id": session.id,
        "topic": topic,
        "events_url": f"/api/events/{session.id}",
    })


async def submit_review(request):
    body = await request.json()
    sid = str(body.get("session_id", ""))
    feedback = str(body.get("feedback", "")).strip()

    session = SESSIONS.get(sid)
    if session is None:
        return JSONResponse({"error": "session not found"}, status_code=404)
    if session.status != "awaiting_review":
        return JSONResponse({"error": f"session not awaiting review (status={session.status})"}, status_code=409)
    if not feedback:
        return JSONResponse({"error": "feedback required"}, status_code=400)

    session.status = "running"
    session.push({"type": "review_submitted", "data": {"feedback": feedback}})
    threading.Thread(target=run_session, args=(session, feedback), daemon=True).start()

    return JSONResponse({"session_id": sid, "status": "resumed"})


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

            # 1. 先把积压事件全部发出去
            while cursor < len(session.events):
                event = session.events[cursor]
                cursor += 1
                payload = json.dumps(event, ensure_ascii=False)
                yield f"id: {cursor}\ndata: {payload}\n\n"

            # 2. 会话终态且事件发完 -> 主动收尾关闭
            if session.status in ("finished", "error") and cursor >= len(session.events):
                yield "event: eos\ndata: {}\n\n"
                break

            # 3. 空闲时等待新事件 (最多 15s)，醒来发心跳保活
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
    Route("/api/start", start_research, methods=["POST"]),
    Route("/api/review", submit_review, methods=["POST"]),
    Route("/api/events/{sid}", stream_events),
    Mount("/static", app=StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static"),
]

app = Starlette(routes=routes)


if __name__ == "__main__":
    print("=" * 60)
    print("  DRS Frontend Server")
    print(f"  ->  http://{HOST}:{PORT}")
    print("=" * 60)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
