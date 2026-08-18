from typing import TypedDict, Annotated
import operator


class ResearchState(TypedDict):
    # -------------------------
    # 1. 用户输入 (Input)
    # -------------------------
    topic: str

    # -------------------------
    # 2. Research 阶段 (规划与检索)
    # -------------------------
    search_queries: list[str]
    research_notes: Annotated[list[str], operator.add]  # 累积检索事实笔记 (带 Reducer 自动追加)
    iteration_count: int                               # 循环检索轮数计数器 (防死循环硬熔断)
    max_iterations: int                                # 最大允许搜索轮数

    # -------------------------
    # 3. Evaluate 阶段 (质检与大纲)
    # -------------------------
    is_sufficient: bool                                # 机器可读的布尔状态 (材料是否充分)
    evaluator_feedback: str                            # 质检评估说明
    outline: str                                       # 研报大纲

    # -------------------------
    # 4. Human Review 阶段 (人工介入与反馈)
    # -------------------------
    human_feedback: str                                # 人类意见摘要
    review_status: str                                 # "approved" (通过) 或 "revision_required" (需修改重审)

    # -------------------------
    # 5. Writer & Output 阶段 (撰写与落盘)
    # -------------------------
    report_content: str                                # 最终生成的长篇 Markdown 研报正文
    output_filepath: str                               # 实体报告落盘路径
