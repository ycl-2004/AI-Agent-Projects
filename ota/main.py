"""
OTA (Omni-channel Ticket Agent) - 交互式主程序入口 (CLI)

提供 3 大模式体验：
1. 【模式 1: 单单即时处理】: 单笔工单两阶段工具调度与 Pydantic 结构化质检 (invoke)
2. 【模式 2: 晨间并发批处理】: 批量并发处理 3~5 张积压工单，秒级完成质检 (batch)
3. 【模式 3: 坐席流式打字输出】: 实时流式生成高情商官方安抚与回复草稿 (stream)

三种模式均支持终端输入；直接按回车即可使用内置默认样例。
"""

import os
import sys
import time

# 确保能正确导入同目录模块
sys.path.insert(0, os.path.dirname(__file__))

from pipeline import process_single_ticket, process_tickets_batch, stream_ticket_reply


def _prompt_text(label: str, default: str) -> str:
    """读取一项终端输入，空输入或非交互环境下回退到默认值。"""
    try:
        value = input(f"👉 {label} (直接回车默认: {default}): ").strip()
    except (EOFError, KeyboardInterrupt):
        value = ""
    return value or default


def _prompt_float(label: str, default: float) -> float:
    """读取金额字段，输入不合法时使用默认值。"""
    value = _prompt_text(label, str(default))
    try:
        return float(value)
    except ValueError:
        print(f"⚠️ 输入不是有效金额，已使用默认值 {default}。")
        return default


def _prompt_int(label: str, default: int) -> int:
    """读取整数业务字段，输入不合法时使用默认值。"""
    value = _prompt_text(label, str(default))
    try:
        return int(value)
    except ValueError:
        print(f"⚠️ 输入不是有效整数，已使用默认值 {default}。")
        return default


def _prompt_ticket(default_ticket: dict, index: int | None = None) -> dict:
    """交互式构造一张工单，保留默认样例作为快速体验路径。"""
    prefix = f"第 {index} 张工单 - " if index is not None else ""
    return {
        "ticket_text": _prompt_text(
            f"{prefix}请输入工单文本", default_ticket["ticket_text"]
        ),
        "user_id": _prompt_text(
            f"{prefix}请输入用户 ID", default_ticket.get("user_id", "user_svip_99")
        ),
        "order_id": _prompt_text(
            f"{prefix}请输入订单号", default_ticket.get("order_id", "ord_1001")
        ),
        "order_amount": _prompt_float(
            f"{prefix}请输入订单金额（元）", default_ticket.get("order_amount", 500.0)
        ),
        "delay_hours": _prompt_int(
            f"{prefix}请输入延误小时数", default_ticket.get("delay_hours", 0)
        ),
    }


def _default_batch_tickets() -> list[dict]:
    """返回批处理模式的内置演示工单。"""
    return [
        {
            "ticket_text": "包裹 ord_1001 延误 48 小时了，明天要出差急用，请尽快送达！",
            "user_id": "user_vip_88",
            "order_id": "ord_1001",
            "order_amount": 800.0,
            "delay_hours": 48,
        },
        {
            "ticket_text": "买的音响包装严重破损，里面零件都掉出来了，要求换货！",
            "user_id": "user_normal_01",
            "order_id": "ord_1002",
            "order_amount": 300.0,
            "delay_hours": 0,
        },
        {
            "ticket_text": "你们这什么破服务？扣了我两次款还没退！再不处理我直接投诉 12315！",
            "user_id": "user_svip_99",
            "order_id": "ord_1003",
            "order_amount": 1500.0,
            "delay_hours": 0,
        },
    ]


def main():
    print("=" * 75)
    print("🎧 欢迎使用 OTA (Omni-channel Ticket Agent) 智能工单质检与分派中台")
    print("=" * 75)
    print("支持以下 3 大运行模式：")
    print("  [1] 单单即时质检与赔付核算 (invoke)")
    print("  [2] 晨间积压工单并发批处理 (batch)")
    print("  [3] 坐席端实时流式回复草稿 (stream)")
    print("=" * 75)

    try:
        choice = input("👉 请选择运行模式 (输入 1 / 2 / 3，直接按回车默认 1): ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        choice = "1"

    if choice == "1":
        # ----------------------------------------------------------------------
        # 模式 1: 单单即时处理
        # ----------------------------------------------------------------------
        print("\n【模式 1: 单单即时质检与赔付核算】")
        ticket_data = _prompt_ticket(
            {
                "ticket_text": (
                    "我的订单 ord_1001 已经延误了 36 个小时还没送到！"
                    "我是 SVIP 会员，你们必须立刻赔偿并告诉我包裹在哪里！"
                ),
                "user_id": "user_svip_99",
                "order_id": "ord_1001",
                "order_amount": 1200.0,
                "delay_hours": 36,
            }
        )
        
        print("\n⏳ 正在启动两阶段工具调用与结构化质检流水线...")
        start_t = time.time()
        resolution = process_single_ticket(ticket_data)
        elapsed = time.time() - start_t
        
        print("\n" + "=" * 75)
        print(f"📊 【工单质检与分派结果】 (处理耗时: {elapsed:.2f}s)")
        print("=" * 75)
        print(f"  • 核心诉求 (summary)         : {resolution.summary}")
        print(f"  • 客户情绪 (customer_sentiment): {resolution.customer_sentiment}")
        print(f"  • 紧急程度 (urgency_level)   : {'🔥' * resolution.urgency_level} ({resolution.urgency_level}/5)")
        print(f"  • 问题分类 (issue_category)   : {resolution.issue_category}")
        print(f"  • 核准赔付 (compensation)    : ¥{resolution.compensation_amount:.2f} 元")
        print(f"  • 是否升级主管 (is_escalated) : {'⚠️ 是' if resolution.is_escalated else '否'}")
        print(f"\n📝 【官方高情商回复草稿】:\n{resolution.official_reply_draft}")
        print("=" * 75)

    elif choice == "2":
        # ----------------------------------------------------------------------
        # 模式 2: 晨间积压工单并发批处理
        # ----------------------------------------------------------------------
        print("\n【模式 2: 晨间积压工单并发批处理 (3 张典型工单同时并发)】")
        use_custom = _prompt_text(
            "是否逐条自定义输入批量工单（输入 y 开始，其他输入使用默认样例）", "n"
        ).lower()
        if use_custom in {"y", "yes", "是"}:
            count = max(1, min(_prompt_int("请输入工单数量（1~5）", 3), 5))
            batch_tickets = [
                _prompt_ticket(
                    {
                        "ticket_text": "请描述客户遇到的问题。",
                        "user_id": "user_normal_01",
                        "order_id": f"ord_10{index}",
                        "order_amount": 500.0,
                        "delay_hours": 0,
                    },
                    index=index,
                )
                for index in range(1, count + 1)
            ]
        else:
            batch_tickets = _default_batch_tickets()

        print(f"⏳ 正在并发并行处理 {len(batch_tickets)} 张积压工单...")
        start_t = time.time()
        results = process_tickets_batch(batch_tickets)
        elapsed = time.time() - start_t

        print(f"\n⚡ 批处理全部完成！总耗时: {elapsed:.2f}s (平均每单 {elapsed/len(results):.2f}s)")
        print("=" * 75)
        for i, res in enumerate(results, start=1):
            print(f"[{i}] 诉求: {res.summary[:20]}... | 情绪: {res.customer_sentiment} | 紧急度: {res.urgency_level} | 赔付: ¥{res.compensation_amount}")
        print("=" * 75)

    elif choice == "3":
        # ----------------------------------------------------------------------
        # 模式 3: 坐席端实时流式回复
        # ----------------------------------------------------------------------
        print("\n【模式 3: 坐席端实时流式打字生成回复】")
        ticket_data = {
            "ticket_text": _prompt_text(
                "请输入客户工单文本", "购买的商品迟迟不发货，客服一直推诿，非常失望！"
            ),
            "user_id": _prompt_text("请输入用户 ID", "user_vip_88"),
        }
        print(f"📥 客户输入: \"{ticket_data['ticket_text']}\"")
        print("\n🖥️ 客服回复实时流式生成: ", end="", flush=True)
        for chunk in stream_ticket_reply(ticket_data):
            print(chunk, end="", flush=True)
            time.sleep(0.01)
        print("\n")


if __name__ == "__main__":
    main()
