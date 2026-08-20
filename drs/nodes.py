import json
import progress
from state import ResearchState
from tools import (
    llm,
    arxiv_paper_search,
    wikipedia_search,
    web_search,
    save_markdown_report,
)

# 建立工具名称索引映射表
tools_by_name = {
    "arxiv_paper_search": arxiv_paper_search,
    "wikipedia_search": wikipedia_search,
    "web_search": web_search,
    "save_markdown_report": save_markdown_report,
}

# 绑定调研相关的 3 个真实搜索工具给模型
search_tools = [arxiv_paper_search, wikipedia_search, web_search]
researcher_llm = llm.bind_tools(search_tools)


# ----------------------------------------------------
# 1. 规划节点 (Planner Node)
# ----------------------------------------------------
def planner_node(state: ResearchState) -> dict:
    """
    规划节点：读取用户主题，拆解为 3 个具体、有深度且互补的搜索子问题。
    """
    topic = state["topic"]
    num_search = 3

    progress.emit({
        "type": "stage", "stage": "planner", "status": "start",
        "message": None, "data": {"topic": topic},
    }, quiet=True)

    prompt = f"""请针对研究主题：“{topic}” 进行深度拆解。
生成 {num_search} 个具体、有深度且适合进一步检索的子问题。
要求：每行输出一个子问题，不要带任何多余的寒暄或序号前缀。"""

    response = llm.invoke(prompt)

    queries = [
        line.strip(" 1234567890.-、")
        for line in response.content.split("\n")
        if line.strip()
    ][:num_search]

    queries_text = "\n".join(f"  {idx}. {q}" for idx, q in enumerate(queries, 1))
    progress.emit({
        "type": "stage", "stage": "planner", "status": "done",
        "message": f"[Planner] 🎯 成功拆解出 {len(queries)} 个搜索子问题:\n{queries_text}",
        "data": {"queries": queries},
    })

    return {"search_queries": queries}


# ----------------------------------------------------
# 2. 深度检索节点 (Research Node)
# ----------------------------------------------------
def research_node(state: ResearchState) -> dict:
    """
    检索节点：让大模型作为智能研究员，针对每个子问题自主决策调用 arXiv、Wikipedia 或 Web 搜索工具，
    并将收集到的真实客观事实汇总为研报笔记 (Research Notes)。
    """
    queries = state.get("search_queries", [])
    collected_notes = []
    current_round = state.get("iteration_count", 0) + 1

    progress.emit({
        "type": "stage", "stage": "research", "status": "start",
        "message": f"\n[Research] 🔍 开始针对 {len(queries)} 个子问题展开多源检索与事实提取...",
        "data": {"round": current_round, "num_queries": len(queries), "queries": queries},
    })

    for query in queries:
        prompt = f"""你是一个专业的高级行业与学术研究员。
当前需要调研的具体问题是：“{query}”

请根据问题的性质自主决定调用最合适的工具：
- 涉及前沿学术架构、算法公式与模型基准 -> 调用 arxiv_paper_search
- 涉及基础概念、权威术语与百科背景 -> 调用 wikipedia_search
- 涉及最新行业新闻、动态动态与工程落地 -> 调用 web_search"""

        ai_msg = researcher_llm.invoke(prompt)

        if ai_msg.tool_calls:
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                if tool_name in tools_by_name:
                    tool = tools_by_name[tool_name]
                    raw_result = tool.invoke(tool_args)

                    note_entry = (
                        f"### 子问题调研: {query}\n"
                        f"**数据源**: {tool_name}\n"
                        f"**提取的事实论据**:\n{raw_result}\n"
                    )
                    collected_notes.append(note_entry)
                    progress.emit({
                        "type": "note", "stage": "research",
                        "message": None,
                        "data": {
                            "query": query,
                            "source": tool_name,
                            "round": current_round,
                            "excerpt": str(raw_result)[:600],
                        },
                    }, quiet=True)
        else:
            note_entry = (
                f"### 子问题调研: {query}\n"
                f"**数据源**: 内部专业知识推理\n"
                f"**事实论据**:\n{ai_msg.content}\n"
            )
            collected_notes.append(note_entry)
            progress.emit({
                "type": "note", "stage": "research",
                "message": None,
                "data": {
                    "query": query,
                    "source": "internal",
                    "round": current_round,
                    "excerpt": str(ai_msg.content)[:600],
                },
            }, quiet=True)

    current_iterations = state.get("iteration_count", 0) + 1

    progress.emit({
        "type": "stage", "stage": "research", "status": "done",
        "message": f"[Research] 收集完成！本轮新增 {len(collected_notes)} 条权威事实笔记 (当前累计迭代: {current_iterations} 轮)",
        "data": {"round": current_iterations, "new_notes": len(collected_notes)},
    })
    return {
        "research_notes": collected_notes,
        "iteration_count": current_iterations,
    }


# ----------------------------------------------------
# 3. 评判与质检节点 (Evaluate Node)
# ----------------------------------------------------
def evaluate_node(state: ResearchState) -> dict:
    """
    质检与反思节点：
    1. 汇总当前累积的所有事实笔记；
    2. 由大模型评估信息充实度：
       - 若材料充足：生成一份结构化研报大纲 (outline)，设置 is_sufficient=True；
       - 若材料仍有盲区：提炼出补充搜索子问题，设置 is_sufficient=False。
    """
    topic = state["topic"]
    notes = state.get("research_notes", [])
    all_notes_text = "\n\n".join(notes)

    progress.emit({
        "type": "stage", "stage": "evaluator", "status": "start",
        "message": f"\n[Evaluator] ⚖️ 正在质检当前累积的 {len(notes)} 条事实材料质量...",
        "data": {"notes_count": len(notes)},
    })

    # 已达最大检索轮数时强制出稿：即使材料不完美，也必须基于现有笔记生成大纲，
    # 避免硬熔断后带着空大纲进入人工审阅。
    at_limit = state.get("iteration_count", 0) >= state.get("max_iterations", 2)
    final_round_note = (
        "\n注意：本轮已是最后一轮检索（已达轮数上限），无论材料是否完美，"
        "都必须基于现有材料生成完整大纲，并将 is_sufficient 置为 true。\n"
        if at_limit else ""
    )

    eval_prompt = f"""你是一个严苛的研报主编兼事实质检员。
当前研报核心主题：【{topic}】
{final_round_note}
以下是研究员目前收集到的所有事实笔记：
{all_notes_text[:3000]}

请对当前收集的信息进行严格质检：
1. 现有信息是否足以撰写一篇涵盖“架构创新、核心机制、参数对比、行业影响”的深度研报？
2. 如果【信息充分】：请生成一份 4~5 个章节的结构化研报大纲 (Markdown 格式)；
3. 如果【信息不足】：请列出 1~2 个亟需补充搜索的核心盲区子问题。

请严格输出为以下 JSON 格式：
{{
  "is_sufficient": true 或 false,
  "outline": "如果充分则输出完整 Markdown 大纲，否则留空字符串",
  "missing_queries": ["如果不足则列出1~2个补充搜索子词", "词2"]
}}
"""

    resp = llm.invoke(eval_prompt)
    raw_content = resp.content.strip()

    if raw_content.startswith("```json"):
        raw_content = raw_content[7:]
    elif raw_content.startswith("```"):
        raw_content = raw_content[3:]
    if raw_content.endswith("```"):
        raw_content = raw_content[:-3]

    try:
        eval_data = json.loads(raw_content.strip())
    except Exception:
        eval_data = {
            "is_sufficient": True,
            "outline": f"# {topic} 深度技术调研报告\n\n## 1. 概述与背景\n## 2. 核心架构与机制创新\n## 3. 性能基准与工程实践\n## 4. 总结与展望",
            "missing_queries": []
        }

    is_sufficient = eval_data.get("is_sufficient", True)

    if is_sufficient:
        outline = eval_data.get("outline", "")
        progress.emit({
            "type": "eval", "stage": "evaluator", "status": "done",
            "message": f"[Evaluator] ✅ 材料充分！已生成初版研报大纲:\n{outline[:150]}...\n",
            "data": {"is_sufficient": True, "outline": outline},
        })
        return {
            "is_sufficient": True,
            "outline": outline,
            "evaluator_feedback": "信息充分，已生成初版大纲"
        }
    else:
        new_queries = eval_data.get("missing_queries", [])
        progress.emit({
            "type": "eval", "stage": "evaluator", "status": "done",
            "message": f"[Evaluator] ⚠️ 发现信息盲区，生成补充搜索问题: {new_queries}",
            "data": {"is_sufficient": False, "missing_queries": new_queries},
        })
        return {
            "is_sufficient": False,
            "search_queries": new_queries,
            "evaluator_feedback": "信息不足，需要补充检索"
        }


# ----------------------------------------------------
# 4. 研究阶段条件路由函数 (Research Router)
# ----------------------------------------------------
def should_continue_research(state: ResearchState) -> str:
    """
    裁判闸门：
    1. 若达到 max_iterations 上限 -> 强制熔断放行 (防止死循环)；
    2. 若评估充分 (is_sufficient=True) -> 放行进入人工审批；
    3. 否则 -> 回跳到 research_node 继续补充搜索！
    """
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 2)

    # 1. 硬熔断检查
    if iteration_count >= max_iterations:
        progress.emit({
            "type": "route", "stage": "evaluator",
            "message": f"\n[Research Router] 🛑 已达到最大允许检索轮数 ({iteration_count}/{max_iterations})，触发硬熔断保护，强制进入人工大纲审批！",
            "data": {"decision": "go_to_review", "reason": "max_iterations"},
        })
        return "go_to_review"

    # 2. 机器可读布尔状态检查
    if state.get("is_sufficient", False):
        progress.emit({
            "type": "route", "stage": "evaluator",
            "message": "\n[Research Router] ✅ 事实材料充实，流向下一步人工大纲审批！",
            "data": {"decision": "go_to_review", "reason": "sufficient"},
        })
        return "go_to_review"

    # 3. 触发反思自愈回路
    progress.emit({
        "type": "route", "stage": "evaluator",
        "message": f"\n[Research Router] 🔄 材料仍有欠缺，触发反思自愈回路，进入第 {iteration_count + 1} 轮补充检索！",
        "data": {"decision": "go_to_research", "reason": "insufficient"},
    })
    return "go_to_research"


# ----------------------------------------------------
# 5. 人工介入与大纲审阅节点 (Reviewer Node with HITL)
# ----------------------------------------------------
from langgraph.types import interrupt


def reviewer_node(state: ResearchState) -> dict:
    """
    人工大纲审阅节点 (HITL)：
    1. 通过 interrupt() 挂起流程，展示当前大纲等待人类反馈；
    2. 接收人类的自然语言输入（通过/小修/重做建议）；
    3. 由 LLM 担任 Feedback Interpreter：
       - 理解人类意图并相应修订大纲；
       - 判断状态是 approved 还是 revision_required；
    4. 返回更新后的 outline、human_feedback 与 review_status。
    """
    topic = state["topic"]
    outline = state.get("outline", "暂无大纲")
    notes = state.get("research_notes", [])

    progress.emit({
        "type": "stage", "stage": "reviewer", "status": "start",
        "message": f"\n[Reviewer] ⏸️ 触发 interrupt() 挂起，等待人工审核大纲...",
        "data": {"outline": outline, "topic": topic, "notes_count": len(notes)},
    })

    human_resp = interrupt(
        f"【待审核研报大纲】 (主题: {topic}):\n\n"
        f"{outline}\n\n"
        f"请审核大纲：\n"
        f"- 直接输入 'yes' / '通过' / 'ok' 批准大纲；\n"
        f"- 或输入具体的修改意见（例如：'增加关于推理成本与竞品对比的章节'）。"
    )

    progress.emit({
        "type": "stage", "stage": "reviewer", "status": "running",
        "message": f"\n[Reviewer] 收到人类反馈: '{human_resp}'，正在由 LLM 深度解析并修订大纲...",
        "data": {"feedback": str(human_resp)},
    })

    prompt = f"""你是一个高级研报编辑部的沟通协调员兼大纲修订师。
研究主题：【{topic}】

【当前大纲】:
{outline}

【人工 Reviewer 的反馈意见】:
{human_resp}

【已收集到的事实资料背景】:
{chr(10).join(notes)[:1500]}

处理规则：
1. 判断 Reviewer 是否认可当前大纲：
   - 若表达明确认可（如“通过”、“可以”、“OK”、“yes”），将 status 设为 "approved"；
   - 若表示认可但提了小幅修改意见，请根据意见修订大纲，并将 status 设为 "approved"；
   - 若明确要求重构或指出重大缺陷（如“不通过”、“重做”、“结构太浅”），将 status 设为 "revision_required"，并根据意见重新调整大纲。
2. 修订大纲时：
   - 优先服从人工 Reviewer 的明确要求；
   - 保持章节逻辑层层递进，适合写成长篇研报。

请严格输出为以下 JSON 格式：
{{
  "status": "approved 或 revision_required",
  "revised_outline": "修改后的完整 Markdown 大纲",
  "review_summary": "用1~2句话总结人类的核心意见"
}}
"""

    response = llm.invoke(prompt)
    raw_content = response.content.strip()

    if raw_content.startswith("```json"):
        raw_content = raw_content[7:]
    elif raw_content.startswith("```"):
        raw_content = raw_content[3:]
    if raw_content.endswith("```"):
        raw_content = raw_content[:-3]

    try:
        review_data = json.loads(raw_content.strip())
    except Exception:
        review_data = {
            "status": "approved" if "yes" in str(human_resp).lower() or "通过" in str(human_resp) else "revision_required",
            "revised_outline": outline,
            "review_summary": str(human_resp)
        }

    status = review_data.get("status", "approved")
    revised_outline = review_data.get("revised_outline", outline)
    summary = review_data.get("review_summary", str(human_resp))

    progress.emit({
        "type": "stage", "stage": "reviewer", "status": "done",
        "message": f"[Reviewer] 大纲处理完成 -> 审批状态: [{status}] | 意见摘要: {summary}",
        "data": {"review_status": status, "outline": revised_outline, "summary": summary},
    })

    return {
        "outline": revised_outline,
        "human_feedback": summary,
        "review_status": status,
    }


# ----------------------------------------------------
# 6. 审核后条件路由函数 (Review Router)
# ----------------------------------------------------
def should_continue_after_review(state: ResearchState) -> str:
    """
    审阅后路由：
    - approved -> 进入长篇撰写 (go_to_writer)
    - revision_required -> 重新进入审阅节点 (go_to_review) 再次让用户确认新大纲！
    """
    status = state.get("review_status", "")

    if status == "approved":
        progress.emit({
            "type": "route", "stage": "reviewer",
            "message": "\n[Review Router] ✅ 大纲审核通过，正式进入长篇撰写阶段！",
            "data": {"decision": "go_to_writer"},
        })
        return "go_to_writer"

    progress.emit({
        "type": "route", "stage": "reviewer",
        "message": "\n[Review Router] 🔄 Reviewer 要求重大修改，将新大纲重新提交人工确认！",
        "data": {"decision": "go_to_review"},
    })
    return "go_to_review"


# ----------------------------------------------------
# 7. 长篇研报撰写节点 (Writer Node)
# ----------------------------------------------------
def writer_node(state: ResearchState) -> dict:
    """
    长篇撰写节点：根据通过的 Outline、Research Notes、Topic 和 Human Feedback 撰写完整报告。
    使用 llm.stream() 逐段产出正文，并通过 progress 事件总线向前端实时流式推送。
    """
    topic = state["topic"]
    outline = state.get("outline", "")
    notes = state.get("research_notes", [])
    feedback = state.get("human_feedback", "")
    all_notes_text = "\n\n".join(notes)

    progress.emit({
        "type": "stage", "stage": "writer", "status": "start",
        "message": f"\n[Writer] ✍️ 正在根据大纲与事实论据撰写长篇深度研究报告...",
        "data": {"topic": topic},
    })

    prompt = f"""你是一个资深的行业首席分析师与科技作家。
请根据以下经过审核的【研报大纲】以及【一手调研事实笔记】，为主题【{topic}】撰写一篇结构严谨、论据详实、排版优雅的长篇深度研究报告。

====================
研报大纲 (结构准绳)
====================
{outline}

====================
一手事实与数据笔记
====================
{all_notes_text[:4000]}

====================
人工编辑重点指导意见
====================
{feedback}

====================
撰写要求
====================
1. 观点必须由事实笔记支撑，严禁凭空捏造数据或参数；
2. 逻辑推进清晰：背景与行业痛点 -> 核心架构与机制创新 -> 性能基准与工程实践 -> 局限性与未来展望；
3. 充分体现专业度与技术深度，语言流畅、排版优雅 (多用小标题、表格、加粗重点)；
4. 直接输出最终的完整 Markdown 格式正文，不要包含任何多余的开场白或自我介绍。
"""

    chunks = []
    for token in llm.stream(prompt):
        delta = token.content
        if not delta:
            continue
        chunks.append(delta)
        progress.emit({
            "type": "chunk", "stage": "writer",
            "message": None,
            "data": {"delta": delta},
        }, quiet=True)

    report = "".join(chunks).strip()

    # 剥掉模型偶尔给整份报告包裹的 markdown 代码围栏 (```markdown ... ```)
    if report.startswith("```") and report.endswith("```"):
        first_newline = report.find("\n")
        if first_newline != -1:
            report = report[first_newline + 1:].rstrip()
            if report.endswith("```"):
                report = report[:-3].rstrip()

    progress.emit({
        "type": "stage", "stage": "writer", "status": "done",
        "message": f"[Writer] ✅ 研报撰写完成！正文总字数: {len(report)} 字符",
        "data": {"chars": len(report)},
    })

    return {
        "report_content": report
    }


# ----------------------------------------------------
# 8. 研报文件落盘节点 (Exporter Node)
# ----------------------------------------------------
def exporter_node(state: ResearchState) -> dict:
    """
    落盘节点：调用 save_markdown_report 工具将生成的研报保存到 outputs 目录。
    """
    topic = state["topic"]
    content = state.get("report_content", "")

    progress.emit({
        "type": "stage", "stage": "exporter", "status": "start",
        "message": f"\n[Exporter] 💾 正在将研报落地保存为本地文件...",
        "data": {},
    })

    # 生成安全文件名
    safe_filename = "".join([c if c.isalnum() or c in "_- " else "_" for c in topic]).strip().replace(" ", "_")
    filename = f"{safe_filename}_deep_research.md"

    filepath = save_markdown_report.invoke({"content": content, "filename": filename})

    progress.emit({
        "type": "stage", "stage": "exporter", "status": "done",
        "message": None,
        "data": {"filepath": filepath},
    }, quiet=True)

    return {
        "output_filepath": filepath
    }
