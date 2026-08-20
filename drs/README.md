# Deep Research & Report System (DRS)
> **基于 LangGraph 的企业级多源深度调研与长篇研报生成智能体系统**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/Framework-LangChain-green.svg)](https://github.com/langchain-ai/langchain)
[![Data Source](https://img.shields.io/badge/Data%20Source-100%25%20Real%20APIs-brightgreen.svg)]()
[![Frontend](https://img.shields.io/badge/Frontend-Starlette%20%2B%20SSE-1D6A50.svg)]()

---

## 📖 项目简介 (Overview)

在实际企业级应用中，面对复杂的行业分析或前沿技术调研，单次 LLM Prompt（One-shot Prompting）往往存在 **“信息滞后、产生幻觉、事实缺乏支撑、输出缺乏深度”** 等致命问题。

**DRS (Deep Research & Report System)** 采用 **“编辑部流水线 (Editorial Pipeline)”** 架构理念，基于 **LangGraph 状态机** 构建。系统将人类专家团队的研究模式转化为严密协同的 Multi-Agent 图拓扑：
- **规划拆解 ──► 100% 真实多源检索 ──► 事实质检与反思自愈 ──► 人机协同大纲终审 (HITL) ──► 深度研报撰写 ──► 实体文件持久化落盘**。

整个系统完全摒弃假数据（Mock），直接打通 **arXiv 学术预印本官方 API**、**Wikipedia 百科官方知识库** 与 **实时互联网搜索引擎**，生成具备工业级参考价值的 3000+ 字技术调研报告。除 CLI 外，项目还提供一个基于 **Starlette + SSE** 的 Web UI：可以实时查看检索进度、在浏览器完成大纲 HITL 审阅，并在线阅读或下载最终研报。

---

## 🏗️ 系统架构与状态机拓扑 (Graph Topology)

系统将确定性业务流与动态自愈回路完美融合，内部包含 **6 个专业业务节点** 与 **2 条条件路由裁判闸门**：

```text
                                  ┌────────────────────────┐
                                  │      START 入口        │
                                  └───────────┬────────────┘
                                              │
                                              ▼
                                  ┌────────────────────────┐
                                  │ 1. Planner Node (规划) │ ──► 意图拆解为 3 个深度子问题
                                  └───────────┬────────────┘
                                              │
                                              ▼
                                  ┌────────────────────────┐
                           ┌─────►│ 2. Research Node(检索) │ ──► ReAct 动态决策调用 arXiv/Wiki/Web
                           │      └───────────┬────────────┘
                           │                  │
                           │                  ▼
                           │      ┌────────────────────────┐
                           │      │ 3. Evaluator (质检反思)│ ──► 评估事实充实度与盲区，生成初版大纲
                           │      └───────────┬────────────┘
                           │                  │
                           │           conditional edge (should_continue_research)
                           │             /         \
                           │      (信息不足)     (信息充分 / 达 max_iterations 硬熔断)
                           └─────── 回路补充        │
                                                    ▼
                                        ┌────────────────────────┐ ◄──────────┐
                                        │ 4. Reviewer Node (HITL)│            │
                                        └───────────┬────────────┘            │
                                                    │ interrupt() 挂起 & resume │ (revision_required)
                                                    ▼                         │
                                             conditional edge ────────────────┘
                                            /                \
                                    (approved)                │
                                       │                      │
                                       ▼                      │
                           ┌────────────────────────┐         │
                           │ 5. Writer Node (撰写)  │         │ ──► 结合大纲、事实笔记与意见写长文
                           └───────────┬────────────┘         │
                                       │                      │
                                       ▼                      │
                           ┌────────────────────────┐         │
                           │ 6. Exporter Node(落盘) │         │ ──► 自动将研报持久化写入 outputs/*.md
                           └───────────┬────────────┘         │
                                       │                      │
                                       ▼                      │
                                      END                     │
```

---

## 🧩 核心节点与职责分工 (Editorial Roles)

| 节点名称 | 编辑部角色 | 核心职责与技术实现 |
|---|---|---|
| **`planner`** | **研究主管** | 深入理解用户调研课题，将其拆解为 3 个互补、高深度、适合检索的具体子问题（`search_queries`）。 |
| **`research`** | **前线调研员** | 使用 `llm.bind_tools` 赋能模型自主感知工具箱，根据子问题属性动态决策调用 arXiv 论文、维基百科或实时 Web 搜索，并将客观事实追加至 `research_notes`（带 Reducer）。 |
| **`evaluator`** | **事实主编** | 汇总已有材料进行严苛质检：<br>• 若材料充足：构思 4~5 个章节的结构化研报大纲，设置 `is_sufficient=True`；<br>• 若有盲区：提炼 1~2 个补充问题，设置 `is_sufficient=False` 触发回跳。 |
| **`reviewer`** | **人类终审闸门** | **HITL（Human-in-the-loop）核心节点**：调用 `interrupt()` 挂起，将大纲呈现给人类主编。通过 LLM Feedback Interpreter 深度解析人类自然语言反馈（支持直接通过、小修优化或推倒重构）。 |
| **`writer`** | **首席科技作家** | 严格以通过的 `outline` 为准绳，以一手 `research_notes` 为论据，结合主编的指导意见，撰写结构严密、排版优雅的长篇 Markdown 深度研报。 |
| **`exporter`** | **排版出版员** | 调用本地落盘工具，自动在 `outputs/` 目录下生成标准 `.md` 文件并返回绝对路径。 |

---

## 🌐 100% 真实外部 API 工具链 (Zero Mock)

系统配备了 4 大生产级原子工具，杜绝任何假数据或固定硬编码：

1. **`arxiv_paper_search` (真实学术论文检索)**：
   - 官方直连 `arxiv.org` API，按关键词实时检索最新预印本论文，提取真实论文标题、作者、发布年份、arXiv 链接与论文完整 Abstract。
2. **`wikipedia_search` (维基百科权威词条检索)**：
   - 官方直连 `Wikipedia API`，自动支持中英文双语回退，检索基础术语标准定义与历史脉络。
3. **`web_search` (互联网实时搜索引擎)**：
   - 直连实时搜索引擎，检索最新发生的产业动态、市场行情、商业发布与竞品评测。
4. **`save_markdown_report` (文件持久化落盘)**：
   - 安全创建 `outputs/` 目录并将内容以 UTF-8 编码落盘。

---

## 📊 状态契约设计 (State Schema & Contract)

在 LangGraph 架构中，State 不仅是存储字典，更是**节点间解耦通信的标准契约**：

```python
from typing import TypedDict, Annotated
import operator

class ResearchState(TypedDict):
    # 1. 输入数据
    topic: str                                         # 用户调研课题

    # 2. 检索阶段 (带 Reducer 累加)
    search_queries: list[str]                          # 拆解出的搜索子问题
    research_notes: Annotated[list[str], operator.add] # 累积的事实笔记 (自动追加)
    iteration_count: int                               # 循环轮数计数器
    max_iterations: int                                # 最大允许轮数 (硬熔断闸门)

    # 3. 质检反思阶段 (机器可读状态)
    is_sufficient: bool                                # 材料是否充足 (True/False)
    evaluator_feedback: str                            # 质检评估意见
    outline: str                                       # 研报大纲

    # 4. 人工审批阶段 (HITL)
    human_feedback: str                                # 人类修改意见摘要
    review_status: str                                 # "approved" (通过) 或 "revision_required" (重构)

    # 5. 撰写与交付产物
    report_content: str                                # 最终生成的长篇研报正文
    output_filepath: str                               # 实体报告保存绝对路径
```

---

## 🛡️ 双重闭环回路与安全防护 (Safety & Reflection)

1. **反思自愈回路 (Reflection Loop)**：
   - 当 `evaluator` 发现信息盲区时，自动生成针对性补充问题并回跳 `research` 节点展开第 2 轮搜索；
   - 配合 `iteration_count >= max_iterations` **硬熔断机制**，坚决防止 Agent 陷入无休止死循环。
2. **人机协同重构回路 (Human Revision Loop)**：
   - Reviewer 节点如果收到主编的重大重构要求（如“结构太浅，重做第二章”），LLM 重新修订大纲后回跳再次挂起，直到主编满意为止。

---

## 🖥️ Web UI 与前端架构 (Frontend)

DRS 前端复用同一个 `graph.py` LangGraph 应用，不另起一套业务逻辑：

```text
浏览器主题输入
      │ POST /api/start
      ▼
frontend/server.py ── 后台线程 ──► graph_app.invoke(initial_state)
      ▲                                  │
      │ GET /api/events/{sid}              │ progress 事件总线 + MemorySaver
      │ SSE 实时事件                       ▼
      └────────────── 浏览器步进器 / 事实流 / HITL 大纲审阅
                         │ POST /api/review
                         └── Command(resume=...) 恢复同一调研会话
```

前端包含三个主要视图：**主题输入** → **调研流水线**（六步进度、事件流、HITL 审阅）→ **研报阅读**（逐字呈现、下载与复制）。前端是纯静态 HTML/CSS/JS，`marked.js` 已本地 vendor，无需 npm 或 Node.js。

---

## 🚀 快速开始与真机体验 (Quick Start)

### 1. 环境准备
确保已安装 Python 3.10+，并在 DRS 项目目录配置 `.env` 文件：
```bash
# 进入 DRS 项目目录
cd projects/drs

# 激活虚拟环境
conda activate LC

# 安装依赖
pip install langgraph langchain langchain-openai ddgs wikipedia arxiv python-dotenv starlette uvicorn

# 使用 DRS 自己的环境变量模板
cp .env.example .env
```

在 `projects/drs/.env` 中配置你的模型与 API 密钥：
```env
MODEL=gpt-4o
BASE_URL=https://api.openai.com/v1
ZAI_API_KEY=your_api_key_here
```

### 2. 启动运行

#### 方式 A：CLI 交互式运行（终端）

CLI 适合快速验证完整链路。启动后输入调研主题；流程到达 Reviewer 节点时，再输入自然语言审核意见：

```bash
cd projects/drs
python main.py
```
**运行效果展示**：
```text
=================================================================
💡 欢迎使用 Deep Research & Report Agent (DRS) 深度研究系统
=================================================================
👉 请输入您想深度调研的主题 (直接按回车默认: 'DeepSeek-V3 架构创新与 MoE 机制'):
> 2026 年具身智能多模态大模型落地现状与挑战
```

如果不想交互输入主题，也可以直接传入命令行参数：

```bash
python main.py "英伟达 Blackwell 架构与 NVLink 5 互联技术深度分析"
```

#### 方式 B：Web UI 运行（浏览器）

Web UI 适合观察实时进度和完成可视化 HITL 审阅。另开一个终端，在 `drs/` 目录启动 Starlette 服务：

```bash
cd projects/drs
python frontend/server.py
```

看到以下地址后，用浏览器打开：

```text
============================================================
  DRS Frontend Server
  ->  http://127.0.0.1:8788
============================================================
```

浏览器中的完整操作流程是：

1. 在首页输入调研主题，点击「开始调研」；
2. 在流水线页面实时查看 Planner、Research、Evaluator 等节点和检索工具事件；
3. 系统到达 `reviewer` 后显示研报大纲，点击「通过」或填写意见后选择「按意见修订大纲」；
4. 等待 Writer 与 Exporter 完成，在研报阅读页查看正文、下载 `.md` 或复制全文。

前端服务默认监听 `127.0.0.1:8788`，健康检查地址为 `http://127.0.0.1:8788/api/health`。CLI 和 Web UI 共用同一套 LangGraph、状态契约、工具和 `outputs/` 落盘逻辑。

---

## 📺 真机运行全流程实录 (Live Demo Walkthrough)

```text
=================================================================
🚀 启动 Deep Research & Report Agent (DRS) 深度调研系统
=================================================================
📌 当前调研主题: 【DeepSeek-V3 架构创新与 MoE 机制】

>>> [Phase 1] 正在进行自主意图拆解、多源真实检索与事实质检...
[Planner] 🎯 成功拆解出 3 个搜索子问题:
  1. DeepSeek-V3 的 MoE 专家动态路由与负载均衡设计机制
  2. 多专家并行训练推理与通信开销优化策略 (PPMoE 等)
  3. MoE 机制与 Transformer 深度融合及参数效率对比

[Research] 🔍 开始针对 3 个子问题展开多源检索与事实提取...
  [Real Tool: Web Search] 正在真实检索互联网网页...
  [Real Tool: arXiv] 正在真实检索学术论文库 -> 'DeepSeek-V3 MoE routing load balancing'
  [Real Tool: arXiv] 正在真实检索学术论文库 -> 'DeepSeek-V3 Transformer parameter efficiency'
[Research] 收集完成！本轮新增 3 条权威事实笔记 (当前累计迭代: 1 轮)

[Evaluator] ⚖️ 正在质检当前累积的 3 条事实材料质量...
[Evaluator] ⚠️ 发现信息盲区，生成针对性补充问题: ['DeepSeek-V3 技术白皮书参数细节', '性能基准测试结果']
[Research Router] 🔄 材料仍有欠缺，触发反思自愈回路，进入第 2 轮补充检索！

[Research] 🔍 展开第 2 轮补充检索...
[Research] 收集完成！本轮新增 2 条权威事实笔记 (当前累计迭代: 2 轮)
[Research Router] 🛑 达到最大允许检索轮数 (2/2)，触发硬熔断保护，进入人工大纲审批！

=================================================================
🔔 [HITL 人工审核闸门] 系统已自动挂起暂停，等待主编审批大纲：
=================================================================
【待审核研报大纲】 (主题: DeepSeek-V3 架构创新与 MoE 机制):
  ## 第一章 引言与背景
  ## 第二章 MoE 架构设计与动态专家选择
  ## 第三章 性能基准与行业对比
  ## 第四章 总结与展望

👉 请输入您的审核意见 (输入 'yes' 直接通过，或输入具体修改要求):
> 通过，但在第二章请务必重点突出专家动态路由与通信开销优化的技术细节。

>>> [Phase 2] 已接收人类反馈，正在唤醒工作流...
[Reviewer] 收到人类反馈，正在由 LLM 深度解析并修订大纲...
[Reviewer] 大纲处理完成 -> 审批状态: [approved] | 意见摘要: 认可大纲，要求第二章重点突出专家动态路由与通信开销优化。
[Review Router] ✅ 大纲审核通过，正式进入长篇撰写阶段！

[Writer] ✍️ 正在根据大纲与一手事实论据撰写长篇深度研究报告...
[Writer] ✅ 研报撰写完成！正文总字符数: 3496 字符

[Exporter] 💾 正在将研报落地保存为本地文件...
  [Real Tool: Save] 研报已成功落盘至真实文件 -> outputs/DeepSeek-V3_架构创新与_MoE_机制_deep_research.md

=================================================================
🎉 深度调研与研报生成全链路圆满完成！
=================================================================
📄 研报落盘文件: outputs/DeepSeek-V3_架构创新与_MoE_机制_deep_research.md
📊 报告总字符数: 3496 字符
```

---

## 🏆 面试亮点与工程设计总结 (Key Engineering Highlights)

如果你在简历或面试中介绍本项目，以下是 **核心工程亮点**：

1. **生产级通信契约设计（Decoupled State Schema）**：
   - 彻底避免传统单一 `feedback` 字段的语义污染，采用 `is_sufficient: bool` 机器状态驱动路由，同时用 `human_feedback` 与 `review_status` 传递自然语言主编意见。
2. **多源真实数据接入与 ReAct 动态工具调度**：
   - 通过 `llm.bind_tools` 让模型具备工具自主感知与动态选择能力，打通 arXiv 学术论文、维基百科与实时 Web，零假数据。
3. **两阶段人机协同生命周期（Two-phase HITL with `interrupt` & `Command`）**：
   - 结合 LangGraph `MemorySaver` Checkpointer 实现断点挂起与恢复；
   - 创新性实现 **LLM Feedback Interpreter**，支持人类模糊的自然语言反馈理解与大纲自适应修订。
4. **反思自愈与硬熔断安全防护（Reflection & Safety Guardrails）**：
   - 具备质检反思回路，当数据不足时自主补充出题再次检索，并配有最大轮数硬熔断，杜绝 Token 浪费与死循环。
