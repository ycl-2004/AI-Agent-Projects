/* ============================================================================
   OTA Frontend — 事件驱动 UI
   事件源：GET /api/events/{sid} (SSE)。服务端保留完整事件日志，
   刷新 / 断线重连后从头回放即可完整重建界面状态（含批处理泳道）。
   ========================================================================== */

(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);

  const STAGES = [
    { key: "prep", name: "预处理" },
    { key: "intent", name: "意图识别" },
    { key: "tools", name: "工具调度" },
    { key: "extract", name: "结构化质检" },
    { key: "report", name: "处置报告" },
  ];

  const TOOL_NAMES = {
    calculate_compensation: "赔付核算",
    check_logistics_status: "物流查询",
    escalate_to_human_manager: "主管升级",
    apply_priority_dispatch: "特急催派",
  };

  const SENTIMENTS = {
    furious: { label: "极度愤怒", cls: "sent-furious" },
    negative: { label: "负面不满", cls: "sent-negative" },
    neutral: { label: "中性", cls: "sent-neutral" },
    positive: { label: "正面", cls: "sent-positive" },
  };

  const CATEGORIES = {
    logistics_delay: "物流延误",
    product_defect: "商品破损",
    billing_issue: "账务问题",
    service_complaint: "服务投诉",
    general_inquiry: "一般咨询",
  };

  const DEFAULT_BATCH = [
    { ticket_text: "包裹 ord_1001 延误 48 小时了，明天要出差急用，请尽快送达！", user_id: "user_vip_88", order_id: "ord_1001", order_amount: 800, delay_hours: 48 },
    { ticket_text: "买的音响包装严重破损，里面零件都掉出来了，要求换货！", user_id: "user_normal_01", order_id: "ord_1002", order_amount: 300, delay_hours: 0 },
    { ticket_text: "你们这什么破服务？扣了我两次款还没退！再不处理我直接投诉 12315！", user_id: "user_svip_99", order_id: "ord_1003", order_amount: 1500, delay_hours: 0 },
  ];

  const state = {
    sessionId: null,
    mode: null,
    es: null,
    terminal: false,
    stage: {},
    tools: 0,
    attempts: 0,
    startedAt: 0,
    elapsedTimer: null,
    batchDone: 0,
    batchTotal: 0,
    streamText: "",
  };

  /* ------------------------------ 工具函数 ------------------------------ */

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmtElapsed(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, "0");
    const s = String(Math.floor(sec % 60)).padStart(2, "0");
    return `${m}:${s}`;
  }

  function elapsed() {
    return state.startedAt ? (Date.now() - state.startedAt) / 1000 : 0;
  }

  function nearBottom() {
    return window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 90;
  }

  function vipOf(userId) {
    const u = String(userId || "").toLowerCase();
    if (u.includes("svip") || u.endsWith("99")) return "SVIP";
    if (u.includes("vip") || u.endsWith("88")) return "VIP";
    return "Normal";
  }

  async function copyText(text, btn, okText = "已复制") {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    const old = btn.textContent;
    btn.textContent = okText;
    setTimeout(() => { btn.textContent = old; }, 1600);
  }

  function hint(sel, text) {
    $(sel).textContent = text || "";
  }

  /* ------------------------------ 视图切换 ------------------------------ */

  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("view-active"));
    $(`#view-${name}`).classList.add("view-active");
    window.scrollTo({ top: 0 });
  }

  function setBadge(el, st, text) {
    el.classList.remove("is-running", "is-ok", "is-err");
    if (st) el.classList.add(`is-${st}`);
    el.querySelector(".status-text").textContent = text;
  }

  /* ------------------------------ 计时器 ------------------------------ */

  function startTimer() {
    stopTimer();
    state.elapsedTimer = setInterval(() => {
      const me = $("#metaElapsed");
      if (me && state.mode === "single") me.textContent = fmtElapsed(elapsed());
      if (state.mode === "batch") updateBatchStats(false);
    }, 1000);
  }

  function stopTimer() {
    if (state.elapsedTimer) { clearInterval(state.elapsedTimer); state.elapsedTimer = null; }
  }

  /* ------------------------------ 会话管理 ------------------------------ */

  function saveSession() {
    sessionStorage.setItem("ota_session", JSON.stringify({ sid: state.sessionId, mode: state.mode }));
  }

  function clearSession() {
    sessionStorage.removeItem("ota_session");
    $("#resumePill").classList.add("hidden");
  }

  function restoreSessionPill() {
    try {
      const saved = JSON.parse(sessionStorage.getItem("ota_session") || "null");
      if (saved && saved.sid && saved.mode) $("#resumePill").classList.remove("hidden");
    } catch { /* ignore */ }
  }

  function resetState() {
    if (state.es) { state.es.close(); state.es = null; }
    stopTimer();
    Object.assign(state, {
      terminal: false, stage: {}, tools: 0, attempts: 0,
      batchDone: 0, batchTotal: 0, streamText: "",
    });
    $("#feed").innerHTML = "";
    $("#lanes").innerHTML = "";
    $("#batchStats").innerHTML = "";
    $("#agentBody").textContent = "";
    $("#agentText").classList.remove("is-done");
    $("#streamActions").classList.add("hidden");
    $("#resumePill").classList.add("hidden");
  }

  async function launch(mode, payload) {
    try {
      const r = await fetch("/api/start", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode, ...payload }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "启动失败");
      beginSession(data.session_id, mode);
    } catch (e) {
      if (mode === "single") hint("#formHint", `启动失败：${e.message}`);
      if (mode === "batch") hint("#batchHint", `启动失败：${e.message}`);
      if (mode === "stream") hint("#streamHint", `启动失败：${e.message}`);
    }
  }

  function beginSession(sid, mode) {
    resetState();
    state.sessionId = sid;
    state.mode = mode;
    state.startedAt = Date.now();
    saveSession();

    if (mode === "stream") {
      showView("stream");
    } else {
      showView("run");
      $("#singleRun").classList.toggle("hidden", mode === "batch");
      $("#batchRun").classList.toggle("hidden", mode !== "batch");
      if (mode === "single") buildStepper();
      setBadge($("#runStatus"), "is-running", "流水线运行中");
    }
    startTimer();
    connect(sid);
  }

  function connect(sid) {
    const es = new EventSource(`/api/events/${sid}`);
    state.es = es;

    es.onmessage = (e) => {
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; }
      handleEvent(ev);
    };

    es.addEventListener("eos", () => {
      state.terminal = true;
      es.close();
    });

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        state.terminal = true;
        clearSession();
        const badge = state.mode === "stream" ? $("#streamStatus") : $("#runStatus");
        setBadge(badge, "is-err", "会话已失效");
      }
    };
  }

  /* ------------------------------ 事件分发 ------------------------------ */

  function laneOf(ev) {
    if (state.mode === "batch" && ev.ticket != null) {
      return document.querySelector(`.lane[data-i="${ev.ticket}"]`) || undefined;
    }
    return undefined;
  }

  function handleEvent(ev) {
    switch (ev.type) {
      case "start": onStart(ev.data); break;
      case "stage": onStage(ev); break;
      case "log": feedLog(ev.text, ev.level || "info", laneOf(ev)); break;
      case "tool":
        if (!ev.ticket) { state.tools++; $("#metaTools").textContent = `${state.tools} 次`; }
        feedTool(ev.name, ev.args, laneOf(ev));
        break;
      case "tool_output": feedToolOutput(ev.output, laneOf(ev)); break;
      case "attempt":
        if (!ev.ticket) { state.attempts++; $("#metaAttempts").textContent = `${state.attempts} 次`; }
        feedLog(`结构化抽取 · 第 ${ev.n} 次尝试`, "info", laneOf(ev));
        break;
      case "validated":
        feedLog("Pydantic 校验通过 · 质检结果就绪", "ok", laneOf(ev));
        if (!ev.ticket) setStage("report", "active");
        break;
      case "result": onResult(ev.data); break;
      case "batch_result": onLaneResult(ev.ticket, ev.data.resolution); break;
      case "batch_error": onLaneError(ev.ticket, ev.data.message); break;
      case "chunk": onChunk(ev.data.text); break;
      case "done": onDone(ev.data); break;
      case "error": onError(ev.data); break;
      case "end":
        state.terminal = true;
        clearSession();
        break;
    }
  }

  /* ------------------------------ start: 初始化视图 ------------------------------ */

  function onStart(data) {
    if (state.mode === "single" && data.ticket) {
      const t = data.ticket;
      $("#runTopic").textContent = t.ticket_text;
      $("#metaSession").textContent = state.sessionId.slice(0, 8);
      $("#metaVip").textContent = vipOf(t.user_id);
      $("#metaOrder").textContent = t.order_id || "—";
      $("#metaAmount").textContent = `¥${Number(t.order_amount || 0).toFixed(2)}`;
      $("#metaDelay").textContent = `${t.delay_hours || 0} h`;
    } else if (state.mode === "batch" && Array.isArray(data.tickets)) {
      state.batchTotal = data.tickets.length;
      state.batchDone = 0;
      buildLanes(data.tickets);
      updateBatchStats(false);
    } else if (state.mode === "stream" && data.ticket) {
      $("#customerBubble").textContent = data.ticket.ticket_text;
      setBadge($("#streamStatus"), "is-running", "回复生成中");
    }
  }

  /* ------------------------------ 步进器 (单工单) ------------------------------ */

  function buildStepper() {
    const el = $("#stepper");
    el.innerHTML = "";
    STAGES.forEach((s, i) => {
      if (i > 0) {
        const link = document.createElement("span");
        link.className = "step-link";
        link.dataset.after = s.key;
        el.appendChild(link);
      }
      const step = document.createElement("span");
      step.className = "step";
      step.dataset.key = s.key;
      step.innerHTML = `<span class="step-dot"></span><span class="step-name">${s.name}</span>`;
      el.appendChild(step);
    });
    state.stage = {};
    renderStepper();
  }

  function setStage(key, st) {
    state.stage[key] = st;
    renderStepper();
  }

  function renderStepper() {
    STAGES.forEach((s, i) => {
      const step = $(`.step[data-key="${s.key}"]`);
      if (!step) return;
      step.classList.remove("is-active", "is-done");
      const st = state.stage[s.key];
      if (st === "active") step.classList.add("is-active");
      if (st === "done") step.classList.add("is-done");

      if (i > 0) {
        const link = $(`.step-link[data-after="${s.key}"]`);
        const prev = state.stage[STAGES[i - 1].key];
        link.classList.toggle("is-passed", prev === "done" || st === "active" || st === "done");
      }
    });
  }

  /* ------------------------------ 事件流渲染 ------------------------------ */

  function feedContainer(lane) {
    return lane ? lane.querySelector(".lane-feed") : $("#feed");
  }

  function appendFeed(el, lane) {
    const container = feedContainer(lane);
    container.appendChild(el);
    if (lane) {
      container.scrollTop = container.scrollHeight;
    } else if (nearBottom()) {
      window.scrollTo({ top: document.documentElement.scrollHeight });
    }
    return el;
  }

  function feedLog(text, level, lane) {
    const t = fmtElapsed(elapsed());
    const div = document.createElement("div");
    div.innerHTML = lane
      ? `<div class="fi fi-${level}"><span class="fi-text">${escapeHtml(text)}</span></div>`
      : `<div class="fi fi-${level}"><span class="fi-time">+${t}</span><span class="fi-text">${escapeHtml(text)}</span></div>`;
    appendFeed(div.firstElementChild, lane);
  }

  function feedTool(name, args, lane) {
    const zh = TOOL_NAMES[name] || "";
    const div = document.createElement("div");
    div.innerHTML = `
      <div class="tool-card">
        <div class="tool-head">
          <span class="tool-badge">${escapeHtml(name)}</span>
          ${zh ? `<span class="tool-zh">${zh}</span>` : ""}
        </div>
        <pre class="tool-pre tool-args">${escapeHtml(args)}</pre>
      </div>`;
    const el = appendFeed(div.firstElementChild, lane);
    feedContainer(lane)._lastTool = el;
  }

  function feedToolOutput(output, lane) {
    const container = feedContainer(lane);
    const last = container._lastTool;
    if (last && last.isConnected) {
      const pre = document.createElement("pre");
      pre.className = "tool-pre tool-out";
      pre.textContent = output;
      last.appendChild(pre);
      if (lane) container.scrollTop = container.scrollHeight;
      else if (nearBottom()) window.scrollTo({ top: document.documentElement.scrollHeight });
    } else {
      feedLog(output, "info", lane);
    }
  }

  /* ------------------------------ 批处理泳道 ------------------------------ */

  function buildLanes(tickets) {
    const lanes = $("#lanes");
    lanes.innerHTML = "";
    tickets.forEach((t, i) => {
      const lane = document.createElement("div");
      lane.className = "lane";
      lane.dataset.i = i;
      lane.innerHTML = `
        <div class="lane-head">
          <span class="lane-idx">T${i + 1}</span>
          <span class="lane-order">${escapeHtml(t.order_id || "—")} · ${escapeHtml(t.user_id)}</span>
          <span class="lane-status"><span class="status-dot"></span><span class="lane-status-text">排队中</span></span>
        </div>
        <p class="lane-text">${escapeHtml(t.ticket_text)}</p>
        <div class="lane-steps">${miniSteps()}</div>
        <div class="lane-feed"></div>
        <div class="lane-result hidden"></div>`;
      lanes.appendChild(lane);
    });
  }

  function miniSteps() {
    return STAGES.map((s, i) => `
      ${i > 0 ? '<span class="ms-link"></span>' : ""}
      <span class="ms" data-key="${s.key}"><span class="ms-dot"></span><span class="ms-name">${s.name}</span></span>`
    ).join("");
  }

  function setLaneStatus(lane, st, text) {
    const status = lane.querySelector(".lane-status");
    status.className = `lane-status ${st ? `is-${st}` : ""}`;
    lane.querySelector(".lane-status-text").textContent = text;
  }

  function onStage(ev) {
    const lane = laneOf(ev);
    if (lane) {
      const ms = lane.querySelector(`.ms[data-key="${ev.key}"]`);
      if (ms) {
        ms.classList.toggle("is-active", ev.state === "active");
        ms.classList.toggle("is-done", ev.state === "done");
        const idx = STAGES.findIndex((s) => s.key === ev.key);
        const link = lane.querySelectorAll(".ms-link")[idx - 1];
        if (link && idx > 0) {
          link.classList.toggle("is-passed", ev.state === "active" || ev.state === "done");
        }
      }
      if (ev.key === "prep" && ev.state === "active") setLaneStatus(lane, "is-running", "处理中");
      return;
    }
    setStage(ev.key, ev.state);
  }

  function updateBatchStats(finished, elapsedSec) {
    const el = $("#batchStats");
    if (finished) {
      el.innerHTML = `全部完成 · <b>${state.batchDone}</b> / ${state.batchTotal} 张 · 总耗时 <b>${fmtElapsed(elapsedSec || elapsed())}</b>`;
    } else {
      el.innerHTML = `完成 <b>${state.batchDone}</b> / ${state.batchTotal} 张 · 已用时 <b>${fmtElapsed(elapsed())}</b>`;
    }
  }

  function onLaneResult(i, res) {
    state.batchDone++;
    updateBatchStats(false);
    const lane = document.querySelector(`.lane[data-i="${i}"]`);
    if (!lane) return;

    lane.querySelectorAll(".ms").forEach((ms) => {
      ms.classList.remove("is-active");
      ms.classList.add("is-done");
    });
    lane.querySelectorAll(".ms-link").forEach((l) => l.classList.add("is-passed"));
    setLaneStatus(lane, "is-ok", "已完成");

    const box = lane.querySelector(".lane-result");
    box.classList.remove("hidden");
    box.innerHTML = `
      <p class="lane-summary">${escapeHtml(res.summary)}</p>
      <div class="lane-chips">
        ${sentimentBadge(res.customer_sentiment)}
        <span class="chip-mini">紧急 ${res.urgency_level}/5</span>
        <span class="chip-mini">${escapeHtml(CATEGORIES[res.issue_category] || res.issue_category)}</span>
        <span class="chip-mini chip-pay">赔付 ¥${Number(res.compensation_amount || 0).toFixed(2)}</span>
        ${res.is_escalated ? '<span class="chip-mini chip-esc">已升级主管</span>' : ""}
      </div>
      <details class="lane-details">
        <summary>官方回复草稿</summary>
        <div class="lane-reply serif">${escapeHtml(res.official_reply_draft)}</div>
      </details>`;
  }

  function onLaneError(i, message) {
    state.batchDone++;
    updateBatchStats(false);
    const lane = document.querySelector(`.lane[data-i="${i}"]`);
    if (!lane) return;
    setLaneStatus(lane, "is-err", "失败");
    feedLog(`处理失败：${message}`, "err", lane);
  }

  /* ------------------------------ 流式回复 ------------------------------ */

  function onChunk(text) {
    state.streamText += text;
    $("#agentBody").textContent = state.streamText;
    if (nearBottom()) window.scrollTo({ top: document.documentElement.scrollHeight });
  }

  /* ------------------------------ 质检报告 (单工单) ------------------------------ */

  function sentimentBadge(v) {
    const s = SENTIMENTS[v] || { label: v, cls: "sent-neutral" };
    return `<span class="badge ${s.cls}"><span class="dot"></span>${s.label}</span>`;
  }

  function uMeter(level) {
    const cls = level >= 4 ? "lvl-hot" : level === 3 ? "lvl-warm" : "lvl-cool";
    let bars = "";
    for (let i = 1; i <= 5; i++) bars += `<span class="u-bar${i <= level ? " is-on" : ""}"></span>`;
    return `<div class="u-meter ${cls}">${bars}</div>`;
  }

  function onResult(data) {
    const r = data.resolution;
    const tiles = $("#tiles");
    tiles.innerHTML = `
      <div class="tile"><p class="tile-label">客户情绪</p><div class="tile-value">${sentimentBadge(r.customer_sentiment)}</div></div>
      <div class="tile"><p class="tile-label">紧急程度</p><div class="tile-value">${uMeter(r.urgency_level)}<span class="tile-sub">${r.urgency_level} / 5</span></div></div>
      <div class="tile"><p class="tile-label">问题分类</p><div class="tile-value"><span class="cat-tag">${escapeHtml(CATEGORIES[r.issue_category] || r.issue_category)}</span></div></div>
      <div class="tile"><p class="tile-label">核准赔付</p><div class="tile-value"><span class="tile-money">¥ ${Number(r.compensation_amount || 0).toFixed(2)}</span></div></div>
      <div class="tile"><p class="tile-label">主管升级</p><div class="tile-value">${r.is_escalated ? '<span class="badge badge-danger"><span class="dot"></span>已升级主管</span>' : '<span class="badge badge-plain"><span class="dot"></span>无需升级</span>'}</div></div>
      <div class="tile"><p class="tile-label">处理耗时</p><div class="tile-value"><span class="tile-time">${Number(data.elapsed || 0).toFixed(1)}s</span></div></div>`;

    const body = $("#replyBody");
    body.innerHTML = "";
    String(r.official_reply_draft || "").split(/\n{2,}/).forEach((p) => {
      if (!p.trim()) return;
      const para = document.createElement("p");
      para.textContent = p.trim();
      body.appendChild(para);
    });

    $("#reportMeta").textContent =
      `SESSION ${state.sessionId.slice(0, 8)} · 工具调用 ${state.tools} 次 · 抽取尝试 ${state.attempts} 次 · 耗时 ${Number(data.elapsed || 0).toFixed(1)}s`;

    $("#reportSummary").textContent = r.summary;
    showView("report");
  }

  /* ------------------------------ 终态 ------------------------------ */

  function onDone(data) {
    stopTimer();
    if (state.mode === "single") {
      setBadge($("#runStatus"), "is-ok", `已完成 · ${Number(data.elapsed || 0).toFixed(1)}s`);
    } else if (state.mode === "batch") {
      setBadge($("#runStatus"), "is-ok", `批处理完成 · ${Number(data.elapsed || 0).toFixed(1)}s`);
      updateBatchStats(true, data.elapsed);
    } else if (state.mode === "stream") {
      setBadge($("#streamStatus"), "is-ok", `已完成 · ${Number(data.elapsed || 0).toFixed(1)}s`);
      $("#agentText").classList.add("is-done");
      $("#streamActions").classList.remove("hidden");
    }
  }

  function onError(data) {
    stopTimer();
    const msg = data && data.message ? data.message : "未知错误";
    if (state.mode === "stream") {
      setBadge($("#streamStatus"), "is-err", "生成失败");
      $("#agentBody").textContent = `生成失败：${msg}`;
    } else {
      setBadge($("#runStatus"), "is-err", "处理失败");
      feedLog(`处理失败：${msg}`, "err");
    }
  }

  /* ------------------------------ 表单与交互 ------------------------------ */

  function buildBatchList() {
    const wrap = $("#batchList");
    wrap.innerHTML = "";
    DEFAULT_BATCH.forEach((t, i) => {
      const item = document.createElement("div");
      item.className = "batch-item";
      item.innerHTML = `
        <div class="batch-item-head">
          <span>T${i + 1} · ${escapeHtml(t.order_id)} · ${escapeHtml(t.user_id)} · ${vipOf(t.user_id)}</span>
          <span>¥${t.order_amount} · 延误 ${t.delay_hours}h</span>
        </div>
        <input type="text" maxlength="1000" value="${escapeHtml(t.ticket_text)}" data-i="${i}">`;
      wrap.appendChild(item);
    });
  }

  function collectBatch() {
    return Array.from(document.querySelectorAll("#batchList input")).map((input, i) => ({
      ...DEFAULT_BATCH[i],
      ticket_text: input.value.trim(),
    })).filter((t) => t.ticket_text);
  }

  function initHome() {
    document.querySelectorAll(".mode-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".mode-tab").forEach((t) => t.classList.remove("is-active"));
        tab.classList.add("is-active");
        const mode = tab.dataset.mode;
        $("#formSingle").classList.toggle("hidden", mode !== "single");
        $("#formBatch").classList.toggle("hidden", mode !== "batch");
        $("#formStream").classList.toggle("hidden", mode !== "stream");
      });
    });

    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        $("#ticketText").value = chip.dataset.text;
        $("#userId").value = chip.dataset.user;
        $("#orderId").value = chip.dataset.order;
        $("#orderAmount").value = chip.dataset.amount;
        $("#delayHours").value = chip.dataset.delay;
        updateVipBadge();
      });
    });

    $("#userId").addEventListener("input", updateVipBadge);

    $("#singleBtn").addEventListener("click", () => {
      const ticket = {
        ticket_text: $("#ticketText").value.trim(),
        user_id: $("#userId").value.trim(),
        order_id: $("#orderId").value.trim(),
        order_amount: parseFloat($("#orderAmount").value) || 0,
        delay_hours: parseInt($("#delayHours").value, 10) || 0,
      };
      if (!ticket.ticket_text) { hint("#formHint", "请输入工单文本"); return; }
      hint("#formHint");
      launch("single", { ticket });
    });

    $("#batchBtn").addEventListener("click", () => {
      const tickets = collectBatch();
      if (!tickets.length) { hint("#batchHint", "至少需要一张工单"); return; }
      hint("#batchHint");
      launch("batch", { tickets });
    });

    $("#streamBtn").addEventListener("click", () => {
      const ticket = {
        ticket_text: $("#streamText").value.trim(),
        user_id: $("#streamUserId").value.trim(),
      };
      if (!ticket.ticket_text) { hint("#streamHint", "请输入客户消息"); return; }
      hint("#streamHint");
      launch("stream", { ticket });
    });

    $("#resumePill").addEventListener("click", () => {
      try {
        const saved = JSON.parse(sessionStorage.getItem("ota_session") || "null");
        if (saved && saved.sid) beginSession(saved.sid, saved.mode);
      } catch { /* ignore */ }
    });

    $("#brandHome").addEventListener("click", (e) => { e.preventDefault(); showView("home"); });
    $("#backBtn").addEventListener("click", () => showView("home"));
    $("#streamBackBtn").addEventListener("click", () => showView("home"));
    $("#streamNewBtn").addEventListener("click", () => { clearSession(); showView("home"); });
    $("#reportNewBtn").addEventListener("click", () => { clearSession(); showView("home"); });

    $("#copyReplyBtn").addEventListener("click", (e) => {
      const paras = Array.from(document.querySelectorAll("#replyBody p")).map((p) => p.textContent).join("\n\n");
      copyText(paras, e.currentTarget);
    });

    $("#copyStreamBtn").addEventListener("click", (e) => {
      copyText(state.streamText, e.currentTarget);
    });

    buildBatchList();
    updateVipBadge();
    restoreSessionPill();
  }

  function updateVipBadge() {
    $("#vipBadge").textContent = vipOf($("#userId").value);
  }

  document.addEventListener("DOMContentLoaded", initHome);
})();
