# AI Agent & Multi-Agent Production Projects
> **面向工业级落地的端到端 AI Agent、工作流编排与 Multi-Agent 实战项目库**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![LangChain](https://img.shields.io/badge/Framework-LangChain-green.svg)](https://github.com/langchain-ai/langchain)
[![Architecture](https://img.shields.io/badge/Architecture-StateGraph%20%2B%20HITL-purple.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

---

## 🎯 仓库定位与愿景 (Vision)

本仓库致力于探索与沉淀 **基于 LangGraph、LangChain、MCP (Model Context Protocol) 与 FastAPI** 的企业级 AI Agent 架构实践。

与简单的单次 Prompt 调用或玩具 Demo 不同，本仓库中的每一个项目都遵循**工业级软件工程标准**：
- **状态机编排 (StateGraph Orchestration)**：确定性业务流与动态循环/反思自愈回路相结合；
- **人机协同治理 (Human-in-the-Loop)**：通过 `interrupt()` 与 `Command(resume=...)` 实现关键业务闸门的人工终审与意见自适应修订；
- **100% 真实外部 API (Zero Mock)**：直连真实数据源（学术论文库、百科知识库、实时搜索引擎），保证业务产物真实可用；
- **解耦通讯契约 (Decoupled Schema)**：机器可读布尔状态驱动路由，自然语言字段承载人类意图，杜绝语义污染。

---

## 🏆 实战项目矩阵 (Projects Matrix)

| 编号 | 项目目录 | 项目全称 | 核心技术栈 | 架构拓扑亮点 | 状态 |
|:---:|:---|:---|:---|:---|:---:|
| **01** | [`drs/`](drs/README.md) | **Deep Research & Report System** | LangGraph + arXiv API + Wikipedia API + Web Search | • 意图拆解与多源真实检索<br>• 事实主编质检与反思自愈回路<br>• HITL 自然语言大纲终审与修订<br>• 3000+ 字长篇技术研报自动撰写与落盘 | ✅ **已就绪** |
| **02** | `planning...` | **Multi-Agent Code Review & Refactor Suite** | LangGraph + MCP + Tree-sitter | 规划中：静态分析、架构审查、自动测试与修复建议的协同智能体 | 🚧 规划中 |
| **03** | `planning...` | **Enterprise RAG & Hybrid Knowledge Graph** | LangGraph + Hybrid Search + Milvus / Neo4j | 规划中：自适应检索路由、GraphRAG 实体抽取与多跳推理 | 🚧 规划中 |

---

## 🛠️ 项目通用工程结构 (Repository Structure)

每个独立项目均遵循模块化、高内聚的标准工程组织：

```text
projects/
├── .gitignore               # 仓库级 Git 忽略规则 (保护密钥并忽略 outputs/ 生成文件)
├── .env.example             # 统一环境变量模板
├── README.md                # 本文档：项目库总览与索引
│
└── drs/                     # 项目 01: Deep Research & Report System
    ├── README.md            # 项目专属架构设计、节点分工与实录文档
    ├── .env.example         # 项目 API 密钥配置模板
    ├── state.py             # 状态契约 (ResearchState) 与 Reducer 定义
    ├── tools.py             # 100% 真实外部工具库 (arXiv, Wiki, Web, FileIO)
    ├── nodes.py             # 6 个核心业务 Node 与 2 个条件边 Router
    ├── graph.py             # StateGraph 拓扑编排与 MemorySaver Checkpointer 编译
    ├── main.py              # CLI 运行入口 (支持交互式自定义课题与默认值)
    └── outputs/             # 研报产物输出目录 (带 .gitkeep 占位)
```

---

## ⚡ 统一环境配置与快速开始 (Getting Started)

### 1. 克隆仓库与配置环境
```bash
# 激活 Python 虚拟环境 (推荐 Python 3.10+)
conda create -n ai-projects python=3.11 -y
conda activate ai-projects

# 安装核心依赖
pip install langgraph langchain langchain-openai ddgs wikipedia arxiv python-dotenv
```

### 2. 配置 API 密钥
复制根目录或项目子目录下的 `.env.example` 为 `.env`：
```bash
cp .env.example .env
```
编辑 `.env` 填入你的模型配置：
```env
MODEL=gpt-4o
BASE_URL=https://api.openai.com/v1
ZAI_API_KEY=your_actual_api_key_here
```

### 3. 运行体验项目

进入目标项目目录并启动：
```bash
cd drs

# 方式 1: 交互式启动 (在终端自由输入你想研究的主题，或按回车使用默认主题)
python main.py

# 方式 2: 命令行快捷启动
python main.py "2026 年具身智能多模态大模型落地现状与挑战"
```

---

## 💡 核心设计原则 (Engineering Philosophy)

1. **真实可用，杜绝 Mock**：
   - 凡涉及外部知识获取，优先接入真实公开 API，拒绝在核心链路中使用硬编码假数据。
2. **状态契约即架构**：
   - 状态机的演进围绕清晰的 `State Schema` 进行，明确区分「机器可读驱动字段」与「自然语言内容字段」。
3. **安全防线第一**：
   - 所有具备回跳反思机制的 Loop 必须包含最大步数（`max_iterations`）硬熔断闸门，严防死循环与 Token 消耗失控。

---

## 📄 开源协议 (License)

本项目采用 [MIT License](LICENSE) 协议开源。欢迎学习、交流与 Star ⭐️！
