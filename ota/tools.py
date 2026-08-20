from datetime import datetime
from langchain_core.tools import tool


# ==============================================================================
# 1. 违约赔付精确财务核算工具
# ==============================================================================
@tool
def calculate_compensation(order_amount: float, delay_hours: int, vip_level: str = "Normal") -> dict:
    """
    根据订单金额、延误时长和客户会员等级，按公司标准财务规则精确核算赔偿现金与补偿券。
    
    :param order_amount: 订单总金额 (单位: 元，例如 500.0)
    :param delay_hours: 延误小时数 (例如 36, 48)
    :param vip_level: 会员等级 (可选: 'Normal', 'VIP', 'SVIP')
    :return: 包含核准赔付金额(compensate_money)与补偿优惠券(additional_rewards)的字典
    """
    if order_amount <= 0 or delay_hours < 0:
        return {"error": "订单金额必须大于0且延误时长不能为负数"}

    vip_upper = vip_level.upper()

    # 延误 <= 24 小时：未严重超标，不赔现金，赠 10 元券
    if delay_hours <= 24:
        return {
            "compensate_money": 0.0,
            "additional_rewards": "10元体验券"
        }

    # 延误 > 48 小时：严重超时，赔付 10% (上限较高)
    if delay_hours > 48:
        rate = 0.10
        if vip_upper == "SVIP":
            compensate_limit = 500.0
        elif vip_upper == "VIP":
            compensate_limit = 200.0
        else:
            compensate_limit = 100.0
        coupon = "50元大额补偿券"
    # 24 < 延误 <= 48 小时：轻度超时，赔付 5%
    else:
        rate = 0.05
        if vip_upper == "SVIP":
            compensate_limit = 200.0
        elif vip_upper == "VIP":
            compensate_limit = 100.0
        else:
            compensate_limit = 50.0
        coupon = "20元立减券"

    calc_money = round(order_amount * rate, 2)
    final_money = min(calc_money, compensate_limit)

    return {
        "compensate_money": final_money,
        "additional_rewards": coupon,
        "vip_level": vip_level,
        "delay_hours": delay_hours
    }


# ==============================================================================
# 2. 真实物流轨迹与滞留原因查询工具
# ==============================================================================
@tool
def check_logistics_status(order_id: str) -> dict:
    """
    查询指定订单的最新物流轨迹、转运节点与滞留异常原因。
    
    :param order_id: 订单编号 (例如 'ord_1001', 'ord_1002', '1003')
    :return: 包含物流节点与异常详情的字典
    """
    # 兼容 'ord_1001'、'ord-1001' 或 '1001' 格式
    clean_id = str(order_id).lower().replace("ord_", "").replace("ord-", "").strip()

    id_to_status = {
        "1001": "华东分拨中心：因暴雨高速封路滞留 36 小时，干线已恢复运输，预计明日送达",
        "1002": "深圳南山网点：派送中外包装破损已转入异常件核验，滞留 52 小时",
        "1003": "北京顺义枢纽：正常中转流转中，无异常滞留，预计今日下午派送"
    }

    status_info = id_to_status.get(clean_id, f"全国干线运输中，当前节点显示已滞留约 30 小时")
    return {
        "order_id": order_id,
        "status": status_info
    }


# ==============================================================================
# 3. 高危客诉人工主管升级工具
# ==============================================================================
@tool
def escalate_to_human_manager(reason: str, urgency: int = 3, customer_sentiment: str = "negative") -> dict:
    """
    当客户情绪极度愤怒 (furious)、产生投诉威胁 (如12315) 或涉及重大损失时，触发二级人工客服主管加急跟进。
    
    :param reason: 升级原因简述 (例如 '客户情绪愤怒威胁投诉12315'、'包裹破损索赔')
    :param urgency: 紧急程度评分 (1~5)
    :param customer_sentiment: 客户情绪 (furious, negative, neutral, positive)
    :return: 包含升级工单号(return_id)与承诺响应时效(return_reply)的字典
    """
    now_str = datetime.now().strftime("%Y%m%d%H%M%S")
    is_critical = (urgency >= 4) or (customer_sentiment.lower() == "furious")

    if is_critical:
        return_id = f"ESC-HIGH-{now_str}"
        return_reply = "已启动红色加急通道：资深客服主管将在 15 分钟内致电联系客户！"
    else:
        return_id = f"ESC-NORM-{now_str}"
        return_reply = "已记录主管待办工单：将在 2 小时内安排专人跟进处理。"

    return {
        "return_id": return_id,
        "return_reply": return_reply,
        "urgency": urgency,
        "reason": reason
    }


# ==============================================================================
# 4. 物流特急催派与派送拦截工具 (完全不重叠的动作执行工具！)
# ==============================================================================
@tool
def apply_priority_dispatch(order_id: str, priority_reason: str) -> dict:
    """
    当包裹发生延误且客户催促时，向快递网点下发特急派送与优先调拨指令。
    
    :param order_id: 订单编号 (例如 'ord_1001')
    :param priority_reason: 催派原因 (例如 '客户明天出差急用', '生鲜快件超时')
    :return: 包含催派指令下发状态与网点响应承诺的字典
    """
    dispatch_code = f"DISP-{datetime.now().strftime('%H%M%S')}"
    return {
        "order_id": order_id,
        "dispatch_code": dispatch_code,
        "dispatch_status": "特急催派指令已下发至末端网点",
        "courier_sla": "网点调度员已锁定包裹，承诺 2 小时内由专属骑手优先派送"
    }


# ==============================================================================
# 5. 工具箱汇总与映射导出
# ==============================================================================
OTA_TOOLS = [
    calculate_compensation,
    check_logistics_status,
    escalate_to_human_manager,
    apply_priority_dispatch
]

OTA_TOOLS_MAP = {t.name: t for t in OTA_TOOLS}
