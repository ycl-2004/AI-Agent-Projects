# DRS Frontend · 深度调研系统 Web UI

「纸墨编辑部」风格的单页 Web 前端 + 零新依赖的 Starlette 后端。

## 运行

```bash
conda activate LC          # 或任何装好 DRS 依赖 (langgraph 等) 的环境
python frontend/server.py
# 浏览器打开 http://127.0.0.1:8788
```

无需 npm / node：前端是纯静态三件套 (`index.html` + `static/style.css` + `static/app.js`)，
marked.js 已本地 vendor 到 `static/vendor/`，完全离线可用。

## 架构

```
浏览器                          frontend/server.py                 graph.py (LangGraph)
──────                          ──────────────────                 ──────────────────
POST /api/start ──────────────► Session + 后台线程 ───────────────► app.invoke(state)
GET  /api/events/{sid} (SSE) ◄─ progress 事件总线 ◄─────────────── 节点/工具 emit()
       │                        (MemorySaver 保存快照)
POST /api/review ◄───────────── interrupt() 挂起 ────────────────► app.invoke(Command(resume=...))
```

- **事件总线**：根目录 `progress.py`。CLI (`python main.py`) 行为不变（事件仅打印终端）；
  Web 模式下工作线程注册 sink，事件实时入 Session 队列。
- **SSE 回放**：服务端保留完整事件日志并按 `Last-Event-ID` 续传，刷新页面 /
  断线重连后前端从头回放即可完整重建 UI 状态（进行中的调研也存于 `sessionStorage`）。
- **HITL**：`reviewer` 节点 `interrupt()` 挂起后，前端弹出大纲审阅文档，
  「通过」或「按意见修订」均通过 `Command(resume=...)` 唤醒同一 thread。

## 前端设计速记

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | `#FAFAF7` | 纸白底 |
| `--ink` | `#1C1B18` | 墨色正文 |
| `--accent` | `#1D6A50` | 墨绿 accent（唯一强调色）|
| `--serif` | Songti SC | 研报正文 / 标题（出版排版）|
| `--mono` | SF Mono | 元数据 / 会话信息 |

三个视图：**主页**（主题输入）→ **调研流水线**（六步步进器 + 事件流 + HITL 审阅文档）
→ **研报阅读**（逐字撰写、终稿排版、下载/复制）。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/start` | `{topic}` → `{session_id}` 启动调研 |
| `GET` | `/api/events/{sid}` | SSE 事件流（支持 `Last-Event-ID` 重连续传）|
| `POST` | `/api/review` | `{session_id, feedback}` HITL 审阅意见，唤醒挂起的流程 |
| `GET` | `/api/health` | 健康检查 |

## 事件类型速查

`stage`(start/done) · `tool`(检索工具调用) · `note`(事实笔记) · `eval`(质检结论)
· `route`(条件路由决策) · `review_required`(HITL 挂起+大纲) · `review_submitted`
· `chunk`(writer 逐字流) · `done`(终稿) · `error` · `end`
