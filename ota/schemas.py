from typing import Optional, Literal
from pydantic import BaseModel, Field

# ==============================================================================
# 1. 业务分类与枚举类型 (Type Aliases)
# ==============================================================================
CustomerSentiment = Literal["furious", "negative", "neutral", "positive"]
IssueCategory = Literal[
    "logistics_delay",     # 物流滞留/延误
    "product_defect",      # 商品破损/质量缺陷
    "billing_issue",       # 支付/扣款/发票问题
    "service_complaint",   # 服务态度投诉
    "general_inquiry"      # 一般性业务咨询
]


# ==============================================================================
# 2. 工单输入模型 (Input Schema)
# ==============================================================================
class TicketInput(BaseModel):
    """前端或外部系统传入的原始工单入参数据"""
    ticket_text: str = Field(description="客户提交的原始工单文本")
    user_id: str = Field(description="客户用户唯一标识")
    order_id: Optional[str] = Field(default=None, description="关联订单号 (若有)")
    order_amount: float = Field(default=0.0, ge=0.0, description="订单金额 (元，不得小于0)")
    delay_hours: int = Field(default=0, ge=0, description="服务或物流延误时长 (小时)")


# ==============================================================================
# 3. 最终工单质检与分派模型 (Output Schema)
# ==============================================================================
class TicketResolution(BaseModel):
    """
    智能客服中台的最终标准化质检与处理报告。
    大模型必须严格按照此 Schema 提取与生成结构化数据。
    """
    # 核心诉求精炼总结 (不超过 30 字)
    summary: str = Field(
        description="客户工单核心诉求的一句话精炼总结 (不超过 30 字)"
    )
    
    # 客户情绪感知
    customer_sentiment: CustomerSentiment = Field(
        description="客户情绪分类：furious(极度愤怒/威胁投诉)、negative(负面/不满)、neutral(中性)、positive(正面/认可)"
    )
    
    # 紧急程度评分 (必须严格限制在 1 到 5 之间)
    urgency_level: int = Field(
        ge=1, le=5,
        description="工单紧急程度评分，整数 1 (极低/普通咨询) 到 5 (极高/严重资损或极度愤怒)"
    )
    
    # 问题分类
    issue_category: IssueCategory = Field(
        description="工单所属的具体业务问题分类"
    )
    
    # 核准赔偿金额 (元，不得小于 0)
    compensation_amount: float = Field(
        default=0.0,
        ge=0.0,
        description="经核算后系统批准的违约赔付或补偿金额 (元)，若无赔付则为 0.0"
    )
    
    # 是否需要主管审核/升级流转
    is_escalated: bool = Field(
        default=False,
        description="当客户情绪极度愤怒或涉及重大资损时，是否已触发人工主管升级流转"
    )
    
    # 高情商官方回复草稿
    official_reply_draft: str = Field(
        description="面向客户的高情商官方回复草稿：包含同理心安抚、赔付说明与清晰的后续解决方案"
    )