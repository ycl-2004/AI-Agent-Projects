"""
OTA (Omni-channel Ticket Agent) - 自动化端到端测试与全链路断言

用于自动化回归测试：
1. 单工单两阶段工具调度与结构化输出准确性
2. 批处理并发并行有效性
3. 流式打字生成有效性
"""

import sys
import os
import time

# 将上级目录加入 sys.path 以便正常引用模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schemas import TicketResolution
from pipeline import process_single_ticket, process_tickets_batch, stream_ticket_reply


def test_single_ticket_resolution():
    print("\n[Test 1] 测试单工单处理与工具调度...")
    ticket = {
        "ticket_text": "我的订单 ord_1001 已经延误了 36 小时还没送达，我是 SVIP 用户，要求立刻赔偿并催派！",
        "user_id": "user_svip_99",
        "order_id": "ord_1001",
        "order_amount": 1000.0,
        "delay_hours": 36
    }
    
    res = process_single_ticket(ticket)
    print("  -> 核心摘要:", res.summary)
    print("  -> 客户情绪:", res.customer_sentiment)
    print("  -> 紧急程度:", res.urgency_level)
    print("  -> 核准赔付:", res.compensation_amount)
    print("  -> 是否升级:", res.is_escalated)
    
    assert isinstance(res, TicketResolution), "返回必须为 TicketResolution 实例！"
    assert res.customer_sentiment in ["furious", "negative", "neutral", "positive"], "情绪枚举必须合法！"
    assert 1 <= res.urgency_level <= 5, "紧急程度必须在 1~5 之间！"
    assert res.compensation_amount >= 0.0, "赔付金额不能为负数！"
    assert len(res.official_reply_draft) > 10, "回复草稿必须为有效长文本！"
    print("✅ [Test 1] 单工单测试断言通过！")


def test_batch_ticket_processing():
    print("\n[Test 2] 测试晨间积压工单并发批处理...")
    tickets = [
        {"ticket_text": "包裹延误 48 小时，急用！", "user_id": "u1", "order_id": "ord_1001", "order_amount": 500, "delay_hours": 48},
        {"ticket_text": "商品包装破损严重，要求换货！", "user_id": "u2", "order_id": "ord_1002", "order_amount": 200, "delay_hours": 0}
    ]
    
    start_t = time.time()
    results = process_tickets_batch(tickets)
    elapsed = time.time() - start_t
    
    print(f"  -> 批处理完成，耗时: {elapsed:.2f}s")
    assert len(results) == len(tickets), "批处理结果数必须与输入工单数一致！"
    assert all(isinstance(r, TicketResolution) for r in results), "所有批处理结果必须为合法模型！"
    print("✅ [Test 2] 批处理测试断言通过！")


def test_stream_ticket_reply():
    print("\n[Test 3] 测试坐席端实时流式回复生成...")
    ticket = {"ticket_text": "你们这什么服务，太差劲了！", "user_id": "u3"}
    
    chunks = list(stream_ticket_reply(ticket))
    full_text = "".join(chunks)
    
    print(f"  -> 接收 Chunk 数量: {len(chunks)}")
    print(f"  -> 完整回复前 50 字: {full_text[:50]}...")
    
    assert len(chunks) >= 1, "流式应至少产生增量 Chunk！"
    assert len(full_text) > 10, "流式回复必须为有效非空文本！"
    print("✅ [Test 3] 流式测试断言通过！")


if __name__ == "__main__":
    print("==================================================================")
    print("🚀 开始运行 OTA 自动化端到端测试")
    print("==================================================================")
    
    test_single_ticket_resolution()
    test_batch_ticket_processing()
    test_stream_ticket_reply()
    
    print("\n==================================================================")
    print("🎉 恭喜！OTA 智能工单质检与分派中台全部测试通过！")
    print("==================================================================")
