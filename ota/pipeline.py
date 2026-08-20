from langchain_core.runnables import (
    RunnableParallel,
    RunnableLambda,
    RunnablePassthrough
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


from tools import OTA_TOOLS, OTA_TOOLS_MAP
from schemas import TicketInput, TicketResolution

import os
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
REPOSITORY_DIR = os.path.dirname(PROJECT_DIR)

# 优先使用 ota/.env，再回退到仓库根目录；最后兼容从其他目录启动时的当前目录配置。
load_dotenv(os.path.join(PROJECT_DIR, ".env"))
load_dotenv(os.path.join(REPOSITORY_DIR, ".env"))
load_dotenv(os.path.join(REPOSITORY_DIR, "..", ".env"))
load_dotenv()

model = ChatOpenAI(
    api_key=os.getenv("ZAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("BASE_URL") or os.getenv("OPENAI_API_BASE"),
    model_name=os.getenv("MODEL", "glm-4-flash"),
    temperature=0.1,
    max_retries=3,
)


def get_customer_vip(input_data):
    """根据 user_id 判断会员等级 (Normal, VIP, SVIP)"""
    if isinstance(input_data, dict):
        user_id = str(input_data.get("user_id", "")).lower()
    else:
        user_id = str(getattr(input_data, "user_id", "")).lower()

    if "svip" in user_id or user_id.endswith("99"):
        return "SVIP"
    elif "vip" in user_id or user_id.endswith("88"):
        return "VIP"
    return "Normal"


def calc_sla_delay(input_data):
    """提取延误小时数"""
    if isinstance(input_data, dict):
        return input_data.get("delay_hours", 0)
    return getattr(input_data, "delay_hours", 0)


def get_current_time(x=None):
    """获取当前时间戳字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ==============================================================================
# 2. 组装数据预处理传送带 (prep_chain)
# ==============================================================================
prep_chain = RunnableParallel(
    ticket_text=RunnableLambda(lambda x: x.get("ticket_text", "") if isinstance(x, dict) else getattr(x, "ticket_text", "")),
    user_id=RunnableLambda(lambda x: x.get("user_id", "guest") if isinstance(x, dict) else getattr(x, "user_id", "guest")),
    order_id=RunnableLambda(lambda x: x.get("order_id", "ord_1001") if isinstance(x, dict) else getattr(x, "order_id", "ord_1001")),
    order_amount=RunnableLambda(lambda x: float(x.get("order_amount", 500.0) if isinstance(x, dict) else getattr(x, "order_amount", 500.0))),
    vip_level=RunnableLambda(get_customer_vip),
    delay_hours=RunnableLambda(calc_sla_delay),
    timestamp=RunnableLambda(get_current_time),
    raw_input=RunnablePassthrough()
)


# ==============================================================================
# 3. 专业工单质检与分派提示词模板 (Prompts)
# ==============================================================================
# 🌟 核心意图感知与工具调度 Prompt (用于第一阶段模型思考与调工具)
ticket_analysis_prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一名资深企业级智能工单质检与售后中台专家。当前系统时间为 [{timestamp}]。

    【客户画像与订单上下文】
    - 用户 ID: {user_id}
    - 会员等级: {vip_level}
    - 关联订单号: {order_id}
    - 订单金额: {order_amount} 元
    - 延误滞留时长: {delay_hours} 小时

    【工作指引与工具调度原则】
    1. 深入感知客户情绪（furious 极度愤怒 / negative 负面不满 / neutral 中性 / positive 正面）；
    2. 若涉及物流轨迹或发货状态查询，调用 `check_logistics_status`；
    3. 若涉及超时滞留索赔，调用 `calculate_compensation` 进行精确财务赔偿与补偿券核算；
    4. 若客户提到急用、出差催促送达，调用 `apply_priority_dispatch` 下发网点特急催派指令；
    5. 若客户极度愤怒、辱骂或威胁向 12315/消协投诉，调用 `escalate_to_human_manager` 触发二级人工主管加急介入。"""),
    ("human", "客户提交的工单原文如下：\n\"{ticket_text}\"")
])

# 🌟 在线客服高情商实时流式回复 Prompt (用于 Mode 3 坐席端实时打字生成)
stream_reply_prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一名具备极高情商与同理心的官方资深客服专家。
    请针对客户的反馈与诉求，生成一份诚恳、温暖且包含具体解决方案的官方回复草稿。
    回复要求：
    1. 首先表达同理心安抚情绪，认可客户的焦急心情；
    2. 明确给出问题目前的处理进展与预计解决时间；
    3. 语气专业、真诚、不推诿。"""),
    ("human", "客户工单：{ticket_text}\n客户等级：{vip_level}\n处理时间：{timestamp}")
])

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from pydantic import ValidationError
from concurrent.futures import ThreadPoolExecutor

stream_chain = prep_chain | stream_reply_prompt | model | StrOutputParser()

# 绑定 4 大原子工具箱
model_with_tools = model.bind_tools(OTA_TOOLS)

# 绑定 Pydantic 结构化输出
structured_model = model.with_structured_output(
    TicketResolution,
    method="function_calling"
)


import time


def invoke_with_retry(runnable, input_payload, max_retries: int = 4, delay: float = 2.5):
    """通用带指数退避的 Runnable 调用包装器，专门抵御 429 限流"""
    for i in range(max_retries):
        try:
            return runnable.invoke(input_payload)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RateLimit" in str(type(e)) or "1305" in err_str:
                wait_time = delay * (i + 1)
                print(f"  ⏳ 触发服务商频控保护 (429)，正在等待 {wait_time:.1f}s 后自动重试 [{i+1}/{max_retries}]...")
                time.sleep(wait_time)
            else:
                raise e
    return runnable.invoke(input_payload)


# ==============================================================================
# 4. 核心端到端工单处理流水线 (两阶段工具调度 + 结构化自愈)
# ==============================================================================
def process_single_ticket(
    ticket_input: dict,
    max_retries: int = 2
) -> TicketResolution:
    """
    单张工单端到端处理流水线：
    Phase 1: 预处理 -> 提示词 -> 模型感知 -> 产出 ToolCall 提案并执行 -> 构造 ToolMessage 闭环
    Phase 2: 回传完整上下文 -> 提取强类型 TicketResolution -> Pydantic 约束校验与自愈重试
    """
    # 1. 运行数据预处理传送带
    context = prep_chain.invoke(ticket_input)
    
    # 2. 格式化第一阶段意图感知 Prompt
    messages: list[BaseMessage] = ticket_analysis_prompt.format_messages(**context)
    
    print(f"  [Step 1] 正在由模型感知意图并进行工具决策...")
    first_resp: AIMessage = invoke_with_retry(model_with_tools, messages)
    
    # 3. 如果模型提议调用工具，执行并回传 ToolMessage
    if first_resp.tool_calls:
        print(f"  🎯 模型决策：识别到需要调用 {len(first_resp.tool_calls)} 个工具！")
        messages.append(first_resp)
        
        for tc in first_resp.tool_calls:
            t_name = tc["name"]
            t_args = tc["args"]
            t_id = tc["id"]
            
            print(f"  🔨 [执行工具] 名称: {t_name} | 参数: {t_args} | ID: {t_id}")
            tool_fn = OTA_TOOLS_MAP.get(t_name)
            
            if tool_fn:
                tool_output = tool_fn.invoke(t_args)
            else:
                tool_output = f"错误：未找到工具 {t_name}"
                
            print(f"  📤 [工具产出] -> {tool_output}")
            messages.append(ToolMessage(content=str(tool_output), tool_call_id=t_id))
    else:
        print("  ℹ️ 模型判断：无需调用外部工具，直接进入质检总结。")

    # 4. 第二阶段：结构化抽取与自愈回路
    extraction_messages = messages + [
        HumanMessage(content="请综合以上所有工单背景与工具执行结果，严格输出最终的标准化工单质检与分派模型 (TicketResolution)。")
    ]
    
    for attempt in range(1, max_retries + 2):
        try:
            print(f"  [Step 2] 正在抽取强类型质检报告 (Attempt {attempt})...")
            result = invoke_with_retry(structured_model, extraction_messages)
            
            if isinstance(result, TicketResolution):
                validated_data = result
            elif isinstance(result, dict):
                validated_data = TicketResolution.model_validate(result)
            else:
                raise ValueError(f"未知结构化输出类型: {type(result)}")
                
            print(f"  ✅ [Attempt {attempt}] TicketResolution Pydantic 校验通过！")
            return validated_data

        except (ValidationError, ValueError) as err:
            print(f"  ⚠️ [Attempt {attempt}] 结构化校验失败: {err}")
            if attempt > max_retries:
                print(f"  🛑 已达最大重试次数 ({max_retries})，触发硬熔断保护！")
                raise err
            
            # 自愈修复：将具体校验错误注入上下文重新抽取
            repair_msg = HumanMessage(
                content=f"上一次提取未通过 Pydantic 校验，报错信息如下：\n{err}\n请重新修正并输出符合规范的模型！"
            )
            extraction_messages.append(repair_msg)


# ==============================================================================
# 5. 多模式批处理与流式接口 (Batch & Stream)
# ==============================================================================
def process_tickets_batch(tickets_list: list[dict]) -> list[TicketResolution]:
    """并发并行批处理多张工单 (适合早高峰积压工单全量质检)"""
    with ThreadPoolExecutor(max_workers=min(len(tickets_list), 5)) as executor:
        results = list(executor.map(process_single_ticket, tickets_list))
    return results


def stream_ticket_reply(ticket_input: dict):
    """实时流式输出对客户的官方回复草稿 (打字机效果)"""
    return stream_chain.stream(ticket_input)
