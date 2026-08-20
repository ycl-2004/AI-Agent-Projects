# OTA Frontend · 智能工单质检 Web UI

「运营指挥台」风格的单页 Web 前端 + 零新依赖的 Starlette 后端。

## 运行

```bash
cd projects/ota
conda activate LC          # 或激活任何装好 OTA 依赖的环境
pip install langchain langchain-openai pydantic python-dotenv starlette uvicorn
cp ../.env.example .env   # 填入 MODEL / BASE_URL / ZAI_API_KEY
python frontend/server.py
# 浏览器打开 http://127.0.0.1:8789
```

启动后可用下面的命令确认服务已就绪：

```bash
curl http://127.0.0.1:8789/api/health
# {"ok":true,"sessions":0}
```

无需 npm / node：前端是纯静态三件套 (`index.html` + `static/style.css` + `static/app.js`)，
不引入任何第三方库，完全离线可用。

## 架构

```
浏览器                          frontend/server.py                 pipeline.py (LCEL)
──────                          ──────────────────                 ─────────────────
POST /api/start ──────────────► Session + 后台线程 ───────────────► process_single_ticket
GET  /api/events/{sid} (SSE) ◄─ stdout 线程分流捕获 ◄────────────── print() 解析为事件
                                (batch: 每单独立线程, 事件带序号)    stream_ticket_reply
```

- **stdout 线程分流**：不改 pipeline.py。工作线程注册 thread-local sink，
  该线程内 pipeline 的 `print` 被解析成结构化事件（工具调用 / 阶段流转 / 自愈重试）；
  CLI (`python main.py`) 行为完全不变。
- **三种模式**：`single` 单工单流水线（步进器 + 事件流 + 元信息卡 → 质检报告视图）、
  `batch` 并发泳道（每张工单一条泳道，各自迷你步进与事件流，完成后就地出结果卡）、
  `stream` 坐席对话（客户气泡 + 打字机官方回复草稿）。
- **环境变量**：`pipeline.py` 优先读取 `ota/.env`，也兼容从仓库根目录读取 `.env`；CLI 与 Web UI 使用同一套模型配置。
- **SSE 回放**：服务端保留完整事件日志并按 `Last-Event-ID` 续传，刷新页面 /
  断线重连后前端从头回放即可完整重建 UI 状态（进行中的会话存于 `sessionStorage`）。

## 前端设计速记

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | `#F6F7F9` | 冷调纸白底 |
| `--ink` | `#191A1E` | 墨色正文 |
| `--accent` | `#3056D3` | 靛蓝 accent（唯一强调色）|
| `--serif` | Songti SC | 官方回复文书 / 报告标题（公文语态）|
| `--mono` | SF Mono | 元数据 / 事件流 / 会话信息 |

语义色只出现在数据处：furious 红 · negative 琥珀 · neutral 灰 · positive 绿；
紧急度 1–5 用量表（低=靛蓝 / 中=琥珀 / 高=红）。

四个视图：**主页**（模式分段 + 工单受理面板）→ **运行流水线**（单工单步进器或批处理泳道）
→ **坐席流式对话** → **质检报告**（六宫格指标 + 官方回复文书）。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/start` | `{mode: single\|batch\|stream, ticket?, tickets?}` → `{session_id}` |
| `GET` | `/api/events/{sid}` | SSE 事件流（支持 `Last-Event-ID` 重连续传）|
| `GET` | `/api/health` | 健康检查 |

## 事件类型速查

`stage`(prep/intent/tools/extract/report 的 active/done，batch 事件带 `ticket` 序号)
· `log`(info/warn 流水线日志) · `tool` / `tool_output`(工具调用与产出)
· `attempt` / `validated`(结构化抽取与 Pydantic 校验) · `result`(单工单 TicketResolution)
· `batch_result` / `batch_error` · `chunk`(流式回复增量) · `done` · `error` · `end`
