# Omni-channel Ticket & Customer Service AI Agent (OTA)
> **基于 LangChain LCEL 的企业级全渠道智能工单质检、赔付核算与分派智能体系统**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangChain](https://img.shields.io/badge/Framework-LangChain%20LCEL-green.svg)](https://github.com/langchain-ai/langchain)
[![Pydantic v2](https://img.shields.io/badge/Validation-Pydantic%20v2-red.svg)](https://docs.pydantic.dev/)
[![Execution](https://img.shields.io/badge/Execution-invoke%20%7C%20batch%20%7C%20stream-purple.svg)]()

---

## 📖 项目简介 (Overview)

在电商、SaaS 与跨国服务场景中，客服中心每天要处理大量来自邮件、App 与社交媒体的售后工单。传统人工处理容易出现 **“响应慢、情绪识别滞后、赔付规则计算易出错、升级不及时”** 等问题。

**OTA (Omni-channel Ticket & Customer Service AI Agent)** 采用 **LangChain LCEL** 组装工单处理流水线，将一张原始客诉转换成可审计的结构化质检结果与官方回复草稿：

- **预处理传送带**：通过 `RunnableParallel`、`RunnableLambda` 与 `RunnablePassthrough` 补齐会员等级、订单信息、延误时长与时间戳。
- **工具调用闭环**：模型根据工单意图选择赔付核算、物流状态、人工升级或特急催派工具，再通过 `ToolMessage` 回传结果。
- **结构化质检与自愈**：使用 Pydantic `TicketResolution` 约束情绪、紧急度、问题分类、赔付金额和官方回复；校验失败时自动修复并重试。
- **三种终端运行模式**：`invoke` 单单处理、`batch` 并发批处理、`stream` 回复草稿流式输出，三种模式均支持终端输入，直接回车可使用默认样例。

OTA 的物流与升级工具目前是本地确定性业务工具，用于演示业务规则和工具调用闭环；项目没有接入真实物流供应商 API。模型调用仍通过 `.env` 中配置的 OpenAI-compatible 接口完成。

---

## 🏗️ 系统架构与数据流 (Architecture & Data Flow)

系统由一条共享的 LCEL 预处理链和三种交付模式组成：

```text
【终端输入工单 / Python 字典】
                │
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 1. prep_chain：LCEL 预处理传送带                                  │
│    RunnableParallel 并行生成 ticket_text、user_id、order_id、       │
│    order_amount、vip_level、delay_hours、timestamp 与 raw_input     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 2. Phase 1：模型意图识别与 Tool Calling                            │
│    model.bind_tools(OTA_TOOLS)                                      │
│    ├─ calculate_compensation                                      │
│    ├─ check_logistics_status                                      │
│    ├─ escalate_to_human_manager                                   │
│    └─ apply_priority_dispatch                                     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ ToolMessage 闭环回传
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 3. Phase 2：结构化质检与自愈重试                                  │
│    with_structured_output(TicketResolution)                        │
│    Pydantic 校验失败 → 注入错误信息 → 重新抽取（默认最多 2 次）     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
       【invoke 单单】   【batch 批处理】    【stream 流式回复】
       TicketResolution  ThreadPoolExecutor  官方回复草稿增量输出
```

---

## 🧩 核心模块与职责分工 (Core Modules)

| 模块 | 核心职责 | 关键实现 |
|---|---|---|
| **`schemas.py`** | 定义工单输入与结构化质检输出契约 | `TicketInput`、`TicketResolution`、`Literal`、`Field` |
| **`tools.py`** | 提供确定性的业务工具函数 | `@tool`、赔付规则、物流状态、升级与催派动作 |
| **`pipeline.py`** | 组装 LCEL 链、工具调度和结构化自愈流程 | `RunnableParallel`、`bind_tools`、`ToolMessage`、`with_structured_output` |
| **`main.py`** | 提供与 DRS 类似的终端交互入口 | 模式选择、字段输入、默认值、结果展示 |
| **`tests/test_pipeline.py`** | 验证单单、批处理与流式接口 | TicketResolution 断言、批量数量断言、stream chunk 断言 |

---

## 🧰 业务工具链 (Business Tools)

1. **`calculate_compensation`（赔付核算）**：按订单金额、延误小时数和会员等级计算现金赔付与补偿券。延误不超过 24 小时时不赔现金；超过 24 小时后按规则计算并受等级上限约束。
2. **`check_logistics_status`（物流状态）**：根据订单号返回本地演示物流节点和滞留原因，内置 `ord_1001`、`ord_1002`、`ord_1003` 示例。
3. **`escalate_to_human_manager`（人工升级）**：针对高紧急度或 `furious` 情绪生成主管升级编号和承诺响应时效。
4. **`apply_priority_dispatch`（特急催派）**：生成催派指令编号，并返回末端网点的处理承诺。

工具执行结果会被转换为 `ToolMessage`，与原始工单一起交给第二阶段结构化抽取。这样模型负责意图判断，业务规则仍由可测试的 Python 函数确定性执行。

---

## 📊 状态契约设计 (Schema & Contract)

OTA 通过 Pydantic 模型约束输入和输出，避免把自然语言回复直接当成业务状态：

```python
class TicketInput(BaseModel):
    ticket_text: str
    user_id: str
    order_id: str | None = None
    order_amount: float = Field(default=0.0, ge=0.0)
    delay_hours: int = Field(default=0, ge=0)


class TicketResolution(BaseModel):
    summary: str
    customer_sentiment: Literal["furious", "negative", "neutral", "positive"]
    urgency_level: int = Field(ge=1, le=5)
    issue_category: Literal[
        "logistics_delay", "product_defect", "billing_issue",
        "service_complaint", "general_inquiry"
    ]
    compensation_amount: float = Field(default=0.0, ge=0.0)
    is_escalated: bool = False
    official_reply_draft: str
```

---

## 🛡️ 自愈机制与安全边界 (Resilience & Guardrails)

1. **结构化输出自愈**：`TicketResolution` 校验失败时，错误信息会被追加到抽取上下文，模型重新生成合规结果；`process_single_ticket` 默认允许 2 次修复重试。
2. **服务商频控保护**：模型调用遇到 `429`、`RateLimit` 或服务商 `1305` 错误时，使用递增等待时间重试，其他异常直接抛出，避免掩盖真正的配置或代码问题。
3. **批处理并发上限**：`process_tickets_batch` 使用线程池，最大并发数不超过 5；CLI 自定义批量输入也限制为 1~5 张工单。
4. **业务规则可测试**：赔付、物流、升级和催派逻辑集中在 `tools.py`，便于单独验证和替换为真实后端 API。

---

## 📂 项目结构 (Project Structure)

```text
projects/ota/
├── README.md               # 项目架构、运行方式与交互实录（本文档）
├── main.py                 # 交互式 CLI：invoke / batch / stream
├── pipeline.py             # LCEL 预处理、工具调用、结构化抽取与 batch/stream 接口
├── schemas.py              # TicketInput 与 TicketResolution Pydantic 契约
├── tools.py                # 4 个本地确定性业务工具及工具映射
└── tests/
    └── test_pipeline.py    # 三种运行模式的自动化回归测试
```

---

## 🚀 快速开始与真机体验 (Quick Start)

### 1. 环境准备

确保已安装 Python 3.10+，在仓库根目录创建并配置 `.env`：

```bash
cd projects
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install langchain langchain-openai pydantic python-dotenv pytest
cp .env.example .env
```

编辑 `.env`，填入 OpenAI-compatible 模型配置：

```env
MODEL=gpt-4o
BASE_URL=https://api.openai.com/v1
ZAI_API_KEY=your_api_key_here
```

### 2. 交互式运行

与 DRS 的终端体验一致：启动后先选择运行模式，再按提示输入工单信息；所有问题直接按回车都可以使用默认值。

```bash
python ota/main.py
```

启动后：

```text
===========================================================================
🎧 欢迎使用 OTA (Omni-channel Ticket Agent) 智能工单质检与分派中台
===========================================================================
支持以下 3 大运行模式：
  [1] 单单即时质检与赔付核算 (invoke)
  [2] 晨间积压工单并发批处理 (batch)
  [3] 坐席端实时流式回复草稿 (stream)
===========================================================================
👉 请选择运行模式 (输入 1 / 2 / 3，直接按回车默认 1): 1
```

#### 模式 1：单单即时处理 (`invoke`)

会依次询问工单文本、用户 ID、订单号、订单金额和延误小时数，然后输出 `TicketResolution`：

```text
👉 请输入工单文本 (直接回车默认: 我的订单 ord_1001 已经延误了 36 个小时还没送到！...):
> 我的包裹延误两天了，我明天要出差，请帮我催派并赔偿。
👉 请输入用户 ID (直接回车默认: user_svip_99):
> user_vip_88
...
⏳ 正在启动两阶段工具调用与结构化质检流水线...
🎯 模型决策：识别到需要调用工具！
✅ [Attempt 1] TicketResolution Pydantic 校验通过！
```

#### 模式 2：批量处理 (`batch`)

先选择是否自定义输入：输入 `y` 后可设置 1~5 张工单并逐条填写；其他输入直接运行内置的 3 张演示工单。批处理使用线程池并发执行。

```text
【模式 2: 晨间积压工单并发批处理 (3 张典型工单同时并发)】
👉 是否逐条自定义输入批量工单（输入 y 开始，其他输入使用默认样例） (直接回车默认: n): y
👉 请输入工单数量（1~5） (直接回车默认: 3): 2
```

#### 模式 3：流式回复 (`stream`)

输入客户工单文本和用户 ID，终端会逐块打印官方回复草稿，形成坐席端打字机效果：

```text
【模式 3: 坐席端实时流式打字生成回复】
👉 请输入客户工单文本 (直接回车默认: 购买的商品迟迟不发货，客服一直推诿，非常失望！):
> 商品一直没有发货，客服也不回复，麻烦尽快处理。
🖥️ 客服回复实时流式生成: 您好，非常抱歉给您带来不好的体验……
```

### 3. 自动化验证

测试会调用配置的模型接口，因此需要先完成 `.env` 配置，并可能产生模型调用费用：

```bash
python ota/tests/test_pipeline.py
# 或
pytest ota/tests/test_pipeline.py -q
```

---

## 💻 Python 调用方式 (Programmatic API)

CLI 之外，也可以在 `ota/` 目录中直接复用三种 pipeline 接口：

```python
from pipeline import (
    process_single_ticket,
    process_tickets_batch,
    stream_ticket_reply,
)

ticket = {
    "ticket_text": "订单 ord_1001 延误 36 小时，请帮忙查询并赔偿。",
    "user_id": "user_svip_99",
    "order_id": "ord_1001",
    "order_amount": 1200.0,
    "delay_hours": 36,
}

resolution = process_single_ticket(ticket)
results = process_tickets_batch([ticket])
reply_chunks = stream_ticket_reply(ticket)
```

---

## 🏆 工程设计亮点 (Key Engineering Highlights)

1. **LCEL 组合式流水线**：把输入预处理、模型推理和输出处理拆成可复用 Runnable，单单、批量和流式模式共享同一套业务上下文。
2. **模型判断与业务执行解耦**：模型只负责选择工具和生成结构化结果，赔付规则、物流状态、升级与催派动作由 Python 工具确定性执行。
3. **强类型业务契约**：用 `TicketInput` 和 `TicketResolution` 将自然语言工单连接到可审计的业务字段，限制情绪枚举、紧急度范围和赔付金额下界。
4. **多模式交互交付**：终端可以像 DRS 一样输入自己的业务内容；同一条链同时支持 `invoke`、`batch` 和 `stream`，方便演示和后续接入服务端。
5. **可替换的工具边界**：当前物流等工具是本地演示实现，后续可在不改变 pipeline 契约的前提下替换成真实订单、物流或 CRM API。
