# OTA (Omni-channel Ticket & Customer Service AI Agent)

> **基于 LangChain LCEL 的企业级全渠道智能工单质检、赔付核算与分派中台**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangChain](https://img.shields.io/badge/Framework-LangChain%20LCEL-green.svg)](https://github.com/langchain-ai/langchain)
[![Pydantic v2](https://img.shields.io/badge/Validation-Pydantic%20v2-red.svg)](https://docs.pydantic.dev/)

---

## 📖 项目简介 (Overview)

在现代电商、SaaS 与跨国服务企业中，客服中心每天面临海量来自邮件、App、社交媒体的售后客诉。传统人工处理存在 **“响应慢、情绪识别滞后、赔付规则计算易出错、SLA 违约”** 等痛点。

**OTA (Omni-channel Ticket Agent)** 是一个完全基于 **LangChain LCEL (LangChain Expression Language)** 构建的生产级智能工单质检与分派中台。它融合了现代大模型工程的四大核心能力：

1. **LCEL 高速数据预处理传送带**：使用 `RunnableParallel`、`RunnablePassthrough` 与 `RunnableLambda` 并发提取用户会员等级、计算 SLA 滞留超时时长并透传原始工单。
2. **原子工具箱动态调度 (Tool Calling)**：大模型自主感知并调用精确赔付核算公式、物流轨迹查询与人工主管升级工具，构造 `ToolMessage` 形成两阶段调用闭环。
3. **Pydantic 结构化质检与自愈重试**：使用 `with_structured_output` 严格提取情绪级别、紧急度（1~5）、赔付金额与官方回复，捕获 `ValidationError` 自动触发自愈回路。
4. **工业级多模式生产运行**：一套 Chain 自动具备 `invoke`（单单即时处理）、`batch`（晨间百单高并发并行处理）、`stream`（坐席实时流式打字生成）。

---

## 🏗️ 系统全景架构与数据流 (Architecture & Data Flow)

```text
                                  【输入工单: {"ticket_text": "...", "user_id": "u99", "order_id": "ord_101"}】
                                                                      │
                                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. LCEL 数据预处理传送带 (Step 1: prep_chain in pipeline.py)                                                                │
│                                                                                                                             │
│                     ┌──► RunnablePassthrough() ──────────────► raw_ticket (原始工单文本)                                   │
│   输入工单字典 ──────┼──► RunnableLambda(get_customer_vip) ───► vip_level ("SVIP" / "Normal")                               │
│                     ├──► RunnableLambda(calc_sla_delay) ────► delay_hours (超时小时数, 如 48h)                             │
│                     └──► RunnableLambda(get_current_time) ──► timestamp (当前时间戳)                                       │
│                                                                                                                             │
│   (RunnableParallel 并发执行并打包为统一上下文 Context 字典)                                                                │
└──────────────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────┘
                                                               │
                                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. 动态原子工具调度与 ToolMessage 闭环 (Step 2: tools.py & Dispatcher)                                                       │
│                                                                                                                             │
│   【大模型意图感知 (Phase 1)】──► 产出 ToolCall 提案 (Proposal)                                                              │
│                                           │                                                                                 │
│               ┌───────────────────────────┴───────────────────────────┐                                                     │
│               ▼                                                       ▼                                                     │
│     calculate_compensation(order_amount, delay_hours, vip_level)    check_logistics_status(order_id)                        │
│     (按财务公式精确计算超时赔付金额与补偿券)                          (查询真实物流滞留与清关状态)                           │
│               │                                                       │                                                     │
│               └───────────────────────────┬───────────────────────────┘                                                     │
│                                           ▼                                                                                 │
│                        【执行本地 Python 工具函数，获取确定性结果】                                                         │
│                                           │                                                                                 │
│                                           ▼                                                                                 │
│                   【构造 ToolMessage(content=result, tool_call_id=...) 闭环回传】                                           │
└──────────────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────┘
                                                               │
                                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. Pydantic 结构化质检与自愈重试 (Step 3: schemas.py & self_healing)                                                         │
│                                                                                                                             │
│   • 严格提取强类型模型 TicketResolution:                                                                                    │
│     ├─ customer_sentiment : Literal["furious", "negative", "neutral", "positive"]                                          │
│     ├─ urgency_level      : int = Field(ge=1, le=5)                                                                         │
│     ├─ issue_category     : Literal["logistics_delay", "product_defect", "billing_issue", "service_complaint"]              │
│     ├─ compensation_amount: float = Field(ge=0.0)                                                                           │
│     ├─ is_escalated       : bool (高怒气/高损失自动触发升级)                                                                │
│     └─ official_reply_draft: str (包含安抚话术、赔付说明与解决方案的官方回复)                                                │
│                                                                                                                             │
│   • 🛡️ 自愈机制: 若模型输出违背约束 (如 urgency=999)，捕获 ValidationError 并重组 Prompt 自动重试 (限 2 次)                │
└──────────────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────┘
                                                               │
                                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. 工业级多模式执行交付 (Step 4: main.py)                                                                                   │
│                                                                                                                             │
│   • 【模式 1: invoke】: 单笔客户工单秒级即时质检与答复生成。                                                                │
│   • 【模式 2: batch】 : 晨间积压工单全并发并行处理 (多线程并发请求，处理 10 张工单仅需单个工单耗时)。                       │
│   • 【模式 3: stream】: 坐席端打字机实时流式输出安抚话术与官方回复草稿。                                                    │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📂 项目模块结构 (Project Structure)

```text
projects/ota/
├── README.md               # 项目架构全景图、设计契约与运行文档 (本文档)
├── schemas.py              # Pydantic 强类型工单契约与质检输出定义 (待实现)
├── tools.py                # 赔付核算、物流追踪、人工升级等原子工具箱 (@tool) (待实现)
├── pipeline.py             # LCEL 数据传送带、两阶段工具调度与自愈控制器 (待实现)
├── main.py                 # 交互式 CLI 主入口 (支持 invoke / batch / stream) (待实现)
└── tests/
    └── test_pipeline.py    # 自动化测试用例与全链路断言 (待实现)
```

---

## 🧩 核心模块职责分工

| 文件名                       | 核心职责                                     | 涉及的 LangChain / Python 核心技术                                                    |
| ---------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------- |
| **`schemas.py`**             | 定义系统入参、工单上下文与最终结构化输出模型 | `pydantic.BaseModel`、`Field(ge=..., le=...)`、`Literal` 枚举                         |
| **`tools.py`**               | 定义模型可调用的原子业务工具                 | `@tool` 装饰器、类型注解、详细参数 Docstring                                          |
| **`pipeline.py`**            | 组装 LCEL 传送带与两阶段工具调度自愈循环     | `RunnableParallel`、`RunnablePassthrough`、`RunnableLambda`、`with_structured_output` |
| **`main.py`**                | 提供友好的终端交互界面与 3 大模式切换        | `chain.invoke()`、`chain.batch()`、`chain.stream()`、终端着色                         |
| **`tests/test_pipeline.py`** | 验证单单处理、并发批处理与流式打字的准确性   | `pytest` / 纯 Python 断言（`assert`）                                                 |

---

## 🚀 你的开发任务清单 (Your Implementation Guide)

本项目的所有骨架与方法签名均已就绪，你只需按以下顺序依次填空实现：

### 📝 Step 1: 在 `schemas.py` 中定义业务模型

- [ ] 定义 `CustomerSentiment`（情绪分类：furious / negative / neutral / positive）
- [ ] 定义 `TicketResolution`（必须包含 `urgency_level` 限制 1~5，`compensation_amount` $\ge 0$）

### 🔨 Step 2: 在 `tools.py` 中实现原子工具箱

- [ ] 实现 `calculate_compensation`：根据订单金额、延误时长与 VIP 级别精确计算违约赔付金；
- [ ] 实现 `check_logistics_status`：模拟返回快递轨迹与滞留原因；
- [ ] 实现 `escalate_to_human_manager`：记录升级工单并返回经理审批流 ID。

### ⚙️ Step 3: 在 `pipeline.py` 中组装 LCEL 管道

- [ ] 组装 `prep_chain`：使用 `RunnableParallel` 并发组合 `RunnablePassthrough` 与 `RunnableLambda`；
- [ ] 实现 `run_ota_pipeline`：两阶段工具调用（第一阶段感知意图调工具，第二阶段回传 `ToolMessage` 并输出结构化 `TicketResolution`）；
- [ ] 实现自愈机制：捕获 `ValidationError` 并将错误信息重组重试。

### 🕹️ Step 4: 在 `main.py` 中实现多模式交互

- [ ] 接入 `invoke`、`batch` 和 `stream`，体验真实客服中台运行效果！

---

## 🏁 快速运行与验证 (Quick Start)

在虚拟环境中使用 `/opt/miniconda3/envs/LC/bin/python` 运行：

```bash
# 1. 运行交互式主程序
/opt/miniconda3/envs/LC/bin/python projects/ota/main.py

# 2. 运行自动化全链路测试
/opt/miniconda3/envs/LC/bin/python projects/ota/tests/test_pipeline.py
```
