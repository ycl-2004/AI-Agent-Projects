"""
Main CLI Entrypoint for Deep Research Agent (DRS).

==============================================================================
运行方式：
  1. 交互式运行 (提示输入主题，支持回车使用默认主题):
     python main.py

  2. 命令行快捷运行 (直接传入自定义主题):
     python main.py "英伟达 Blackwell 架构与 NVLink 互联技术分析"
     python main.py "2026 年具身智能多模态大模型落地现状"

流转全流程：
  Phase 1: 自主意图拆解 -> 多源真实检索 (arXiv/Wiki/Web) -> 事实质检反思 -> interrupt() 挂起
  Phase 2: 用户审核大纲并输入意见 -> 唤醒图流转 -> 长文撰写 -> 自动落盘 outputs/
==============================================================================
"""

import sys
import uuid
from langgraph.types import Command
from graph import app


def run_deep_research(topic: str = "DeepSeek-V3 架构创新与 MoE 机制", default_review_input: str = None):
    print("\n" + "=" * 65)
    print("🚀 启动 Deep Research & Report Agent (DRS) 深度调研系统")
    print("=" * 65)
    print(f"📌 当前调研主题: 【{topic}】\n")

    # 1. 为本次调研生成唯一 Thread ID (用于 Checkpointer 会话持久化与挂起)
    thread_id = f"research-session-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    # 2. 初始化图状态
    initial_state = {
        "topic": topic,
        "search_queries": [],
        "research_notes": [],
        "iteration_count": 0,
        "max_iterations": 2,
        "is_sufficient": False,
        "evaluator_feedback": "",
        "outline": "",
        "human_feedback": "",
        "review_status": "",
        "report_content": "",
        "output_filepath": "",
    }

    # ----------------------------------------------------
    # Phase 1: 启动工作流并运行至 Reviewer 中断挂起
    # ----------------------------------------------------
    print(">>> [Phase 1] 正在进行自主意图拆解、多源真实检索与事实质检...")
    result_phase1 = app.invoke(initial_state, config=config)

    # 检查是否成功触发 interrupt 挂起
    if "__interrupt__" in result_phase1:
        interrupt_info = result_phase1["__interrupt__"][0].value
        print("\n" + "=" * 65)
        print("🔔 [HITL 人工审核闸门] 系统已自动挂起暂停，等待主编审批大纲：")
        print("=" * 65)
        print(interrupt_info)
        print("=" * 65)

        if default_review_input:
            user_decision = default_review_input
            print(f"\n👉 [自动注入主编意见]: {user_decision}")
        else:
            try:
                user_decision = input("\n👉 请输入您的审核意见 (输入 'yes' 直接通过，或输入具体修改要求):\n> ").strip()
                if not user_decision:
                    user_decision = "yes，大纲合理，请开始撰写正文。"
            except Exception:
                user_decision = "yes，大纲合理，请开始撰写正文。"

        print(f"\n>>> [Phase 2] 已接收人类反馈: '{user_decision}'，正在唤醒工作流...")

        # ----------------------------------------------------
        # Phase 2: 使用 Command(resume=...) 带着用户输入恢复执行
        # ----------------------------------------------------
        result_phase2 = app.invoke(
            Command(resume=user_decision),
            config=config
        )

        print("\n" + "=" * 65)
        print("🎉 深度调研与研报生成全链路圆满完成！")
        print("=" * 65)
        print(f"📄 研报落盘文件: {result_phase2.get('output_filepath')}")
        print(f"📊 报告总字符数: {len(result_phase2.get('report_content', ''))} 字符")
        print("\n--- 研报正文预览 (前 400 字) ---")
        print(result_phase2.get("report_content", "")[:400] + "\n...")

        return result_phase2

    else:
        print("工作流未触发中断，直接执行完毕。")
        return result_phase1


if __name__ == "__main__":
    default_topic = "DeepSeek-V3 架构创新与 MoE 机制"

    # 1. 如果命令行带有参数: python main.py "你的主题"
    if len(sys.argv) > 1:
        target_topic = " ".join(sys.argv[1:]).strip()
    else:
        # 2. 如果直接运行 python main.py: 交互式提示用户输入
        print("=" * 65)
        print("💡 欢迎使用 Deep Research & Report Agent (DRS) 深度研究系统")
        print("=" * 65)
        try:
            user_input = input(f"👉 请输入您想深度调研的主题 (直接按回车默认: '{default_topic}'):\n> ").strip()
            target_topic = user_input if user_input else default_topic
        except Exception:
            target_topic = default_topic

    run_deep_research(target_topic)
