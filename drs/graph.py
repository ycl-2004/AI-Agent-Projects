"""
Graph Topology and Assembly for Deep Research Agent.

==============================================================================
完整图拓扑编排 (StateGraph):
  START ──► planner ──► research ──► evaluator ──┬─ (信息不足) ──► research (自愈回路)
                                                 └─ (充分/超限) ─► reviewer (HITL 挂起)
                                                                       │
                                                       ┌───────────────┴───────────────┐
                                                       │                               │
                                            (revision_required)                   (approved)
                                                       │                               │
                                                       ▼                               ▼
                                                   reviewer                          writer
                                                                                       │
                                                                                       ▼
                                                                                    exporter
                                                                                       │
                                                                                       ▼
                                                                                      END
==============================================================================
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from state import ResearchState
from nodes import (
    planner_node,
    research_node,
    evaluate_node,
    should_continue_research,
    reviewer_node,
    should_continue_after_review,
    writer_node,
    exporter_node,
)

# 1. 创建图构造器
builder = StateGraph(ResearchState)

# 2. 注册 6 个核心业务节点
builder.add_node("planner", planner_node)
builder.add_node("research", research_node)
builder.add_node("evaluator", evaluate_node)
builder.add_node("reviewer", reviewer_node)
builder.add_node("writer", writer_node)
builder.add_node("exporter", exporter_node)

# 3. 编排确定性流转边
builder.add_edge(START, "planner")
builder.add_edge("planner", "research")
builder.add_edge("research", "evaluator")

# 4. 编排第一条条件边：事实质检与反思回路
builder.add_conditional_edges(
    "evaluator",
    should_continue_research,
    {
        "go_to_research": "research",  # 信息不足，回跳第 2 轮深度补充检索
        "go_to_review": "reviewer",    # 信息充实或达到上限，流向人工审批
    }
)

# 5. 编排第二条条件边：人工大纲审阅与修改回路
builder.add_conditional_edges(
    "reviewer",
    should_continue_after_review,
    {
        "go_to_review": "reviewer",    # 人工要求重构大纲，重新提交人工审核
        "go_to_writer": "writer",      # 大纲通过，进入长篇研报正文撰写
    }
)

# 6. 撰写完成自动流向落盘并结束
builder.add_edge("writer", "exporter")
builder.add_edge("exporter", END)

# 7. 挂载 Checkpointer 编译 (为 HITL interrupt/resume 存储快照)
checkpointer = MemorySaver()
app = builder.compile(checkpointer=checkpointer)
