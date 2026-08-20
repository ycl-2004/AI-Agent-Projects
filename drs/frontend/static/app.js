/* ============================================================================
   DRS Frontend — 事件驱动 UI
   事件源：GET /api/events/{sid} (SSE)，服务端保留完整事件日志，
   刷新 / 断线重连后从头回放即可完整重建界面状态。
   ========================================================================== */

(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);

  const STAGES = [
    { key: "planner", name: "意图拆解" },
    { key: "research", name: "多源检索" },
    { key: "evaluator", name: "事实质检" },
    { key: "reviewer", name: "主编审阅" },
    { key: "writer", name: "研报撰写" },
    { key: "exporter", name: "落盘导出" },
  ];

  const SOURCES = {
    arxiv_paper_search: { label: "arXiv", cls: "src-arxiv" },
    wikipedia_search: { label: "Wikipedia", cls: "src-wiki" },
    web_search: { label: "Web", cls: "src-web" },
    internal: { label: "内部推理", cls: "src-llm" },
  };

  const TOOL_LABELS = { arxiv: "arXiv", wikipedia: "Wikipedia", web: "Web" };

  const APPROVE_DEFAULT = "yes，大纲合理，请开始撰写正文。";

  const state = {
    sessionId: null,
    topic: "",
    terminal: false,          // finished | error 后为 true
    es: null,
    stage: {},                // key -> pending | active | done
    stats: { round: 0, notes: 0, arxiv: 0, wiki: 0, web: 0 },
    reportText: "",
    reportFilepath: "",
    streamBuf: "",
    streamTimer: 0,
    writing: false,
    startedAt: 0,
    elapsedTimer: null,
    userScrolled: false,
    seenEvents: 0,
  };

  /* ------------------------------ 工具函数 ------------------------------ */

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function mdToHtml(md) {
    if (typeof marked === "undefined") return `<pre>${escapeHtml(md)}</pre>`;
    return marked.parse(md, { gfm: true, breaks: false });
  }

  function fmtElapsed(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, "0");
    const s = String(Math.floor(sec % 60)).padStart(2, "0");
    return `${m}:${s}`;
  }

  function nearBottom() {
    return window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 90;
  }

  /* ------------------------------ 视图切换 ------------------------------ */

  function showView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("view-active"));
    $(`#view-${name}`).classList.add("view-active");
    window.scrollTo({ top: 0 });
  }

  /* ------------------------------ 步进器 ------------------------------ */

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

  function setStage(key, st) { state.stage[key] = st; renderStepper(); }

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

  /* ------------------------------ 状态徽标 ------------------------------ */

  function setStatus(kind, text) {
    const badge = $("#runStatus");
    badge.className = "status-badge";
    if (kind) badge.classList.add(`is-${kind}`);
    $("#runStatusText").textContent = text;
  }

  /* ------------------------------ 事件流卡片 ------------------------------ */

  function feedAppend(el, { banner = false } = {}) {
    const feed = $("#feed");
    const stick = nearBottom();
    feed.appendChild(el);
    if (stick && !banner) {
      el.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }

  function elFromHtml(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  function addBanner(text) {
    feedAppend(elFromHtml(`<div class="feed-banner">${escapeHtml(text)}</div>`), { banner: true });
  }

  function addPlannerCard(queries) {
    const items = queries.map((q) => `<li>${escapeHtml(q)}</li>`).join("");
    feedAppend(elFromHtml(`
      <div class="fcard">
        <div class="fcard-head"><span class="src-badge src-llm">PLANNER</span><span class="fcard-title">拆解出 ${queries.length} 个搜索子问题</span></div>
        <ol class="fcard-queries">${items}</ol>
      </div>`));
  }

  function addToolLine(tool, query) {
    const label = TOOL_LABELS[tool] ?? SOURCES[tool]?.label ?? tool;
    feedAppend(elFromHtml(`
      <div class="fline"><span class="fline-src">${escapeHtml(label)}</span><span>${escapeHtml(query)}</span></div>`));
  }

  function addRouteLine(text) {
    feedAppend(elFromHtml(`<div class="fline"><span>${escapeHtml(text.replace(/^\s*[\u2192>]+\s*/, ""))}</span></div>`));
  }

  function addNoteCard(data) {
    const src = SOURCES[data.source] ?? { label: data.source, cls: "src-llm" };
    const card = elFromHtml(`
      <div class="fcard fcard-note">
        <div class="fcard-head">
          <span class="src-badge ${src.cls}">${escapeHtml(src.label)}</span>
          <span class="fcard-query">${escapeHtml(data.query)}</span>
        </div>
        <div class="note-excerpt">${escapeHtml(data.excerpt)}</div>
        <button class="note-toggle" type="button">展开全文</button>
      </div>`);
    const excerpt = card.querySelector(".note-excerpt");
    const toggle = card.querySelector(".note-toggle");
    toggle.addEventListener("click", () => {
      const open = excerpt.classList.toggle("is-open");
      toggle.textContent = open ? "收起" : "展开全文";
    });
    feedAppend(card);
  }

  function addEvalCard(data) {
    if (data.is_sufficient) {
      feedAppend(elFromHtml(`
        <div class="fcard fcard-eval is-ok">
          <div class="fcard-verdict"><span class="fcard-title">材料充分 · 已生成初版大纲，送主编审阅</span></div>
        </div>`));
    } else {
      const chips = (data.missing_queries || []).map((q) => `<span>${escapeHtml(q)}</span>`).join("");
      feedAppend(elFromHtml(`
        <div class="fcard fcard-eval is-gap">
          <div class="fcard-verdict"><span class="fcard-title">发现信息盲区 · 触发补充检索</span></div>
          <div class="fcard-missing">${chips}</div>
        </div>`));
    }
  }

  function addReviewDoneCard(data) {
    const ok = data.review_status === "approved";
    feedAppend(elFromHtml(`
      <div class="fcard">
        <div class="fcard-head">
          <span class="src-badge ${ok ? "src-arxiv" : "src-llm"}">${ok ? "APPROVED" : "REVISE"}</span>
          <span class="fcard-title">${escapeHtml(data.summary || (ok ? "大纲审核通过" : "要求修订大纲"))}</span>
        </div>
      </div>`));
  }

  function addErrorCard(msg) {
    feedAppend(elFromHtml(`
      <div class="fcard fcard-error"><strong>调研流程出错</strong><br>${escapeHtml(msg)}</div>`));
  }

  /* ------------------------------ 统计侧栏 ------------------------------ */

  function updateMeta() {
    $("#metaSession").textContent = state.sessionId ? state.sessionId.slice(0, 8) : "—";
    $("#metaRound").textContent = `${state.stats.round} / 2`;
    $("#metaNotes").textContent = `${state.stats.notes} 条`;
    $("#metaArxiv").textContent = state.stats.arxiv;
    $("#metaWiki").textContent = state.stats.wiki;
    $("#metaWeb").textContent = state.stats.web;
  }

  function startClock() {
    stopClock();
    state.startedAt = Date.now();
    state.elapsedTimer = setInterval(() => {
      $("#metaElapsed").textContent = fmtElapsed((Date.now() - state.startedAt) / 1000);
    }, 1000);
  }

  function stopClock() {
    if (state.elapsedTimer) clearInterval(state.elapsedTimer);
    state.elapsedTimer = null;
  }

  /* ------------------------------ 进入各视图 ------------------------------ */

  function enterPipeline(topic, sessionId) {
    state.topic = topic;
    state.sessionId = sessionId;
    state.terminal = false;
    state.reportText = "";
    state.streamBuf = "";
    state.writing = false;
    state.stats = { round: 0, notes: 0, arxiv: 0, wiki: 0, web: 0 };
    $("#runTopic").textContent = topic;
    $("#feed").innerHTML = "";
    $("#reviewPanel").classList.add("hidden");
    $("#runBody").classList.remove("hidden");
    $("#feedbackInput").value = "";
    $("#reportBody").innerHTML = "";
    $("#reportBody").classList.remove("is-writing");
    $("#reportActions").classList.add("hidden");
    $("#writingBanner").classList.add("hidden");
    $("#reportTitle").textContent = topic;
    $("#reportMeta").textContent = "";
    setStatus("running", "调研中");
    buildStepper();
    updateMeta();
    startClock();
    sessionStorage.setItem("drs-session", JSON.stringify({ id: sessionId, topic }));
    showView("pipeline");
  }

  function goHome({ keepSession = false } = {}) {
    if (state.es) { state.es.close(); state.es = null; }
    stopClock();
    if (!keepSession) {
      state.sessionId = null;
      state.terminal = true;
      sessionStorage.removeItem("drs-session");
    }
    refreshResumePill();
    showView("home");
  }

  function refreshResumePill() {
    const pill = $("#resumePill");
    if (state.sessionId && !state.terminal) {
      pill.classList.remove("hidden");
      pill.textContent = `继续「${state.topic.length > 18 ? state.topic.slice(0, 18) + "…" : state.topic}」的调研 →`;
    } else {
      pill.classList.add("hidden");
    }
  }

  /* ------------------------------ SSE 连接 ------------------------------ */

  function connectSSE(sessionId) {
    if (state.es) state.es.close();
    const es = new EventSource(`/api/events/${sessionId}`);
    state.es = es;

    es.onmessage = (e) => {
      try {
        handleEvent(JSON.parse(e.data));
      } catch (err) {
        console.error("event parse error", err);
      }
    };

    es.addEventListener("eos", () => { es.close(); });

    es.onerror = () => {
      /* EventSource 会携带 Last-Event-ID 自动重连，服务端从断点继续回放 */
    };
  }

  /* ------------------------------ 事件分发 ------------------------------ */

  function handleEvent(ev) {
    const d = ev.data || {};
    switch (ev.type) {

      case "stage": {
        const key = ev.stage;
        if (!key || !STAGES.some((s) => s.key === key)) break;
        if (ev.status === "start") setStage(key, "active");
        if (ev.status === "done") setStage(key, "done");

        if (key === "planner" && ev.status === "done") addPlannerCard(d.queries || []);

        if (key === "research" && ev.status === "start") {
          state.stats.round = d.round ?? state.stats.round;
          updateMeta();
          if ((d.round ?? 1) > 1) addBanner(`第 ${d.round} 轮补充检索`);
        }

        if (key === "evaluator" && ev.status === "start") {
          setStage("research", "done");
        }

        if (key === "reviewer" && ev.status === "start") {
          /* 注意：resume 后 reviewer 节点会从头重跑一次，banner 统一放在 review_required 里，避免重复 */
        }

        if (key === "writer" && ev.status === "start") {
          reportStart();
        }

        if (key === "exporter" && ev.status === "done" && d.filepath) {
          state.reportFilepath = d.filepath;
        }
        break;
      }

      case "tool": {
        if (d.tool && TOOL_LABELS[d.tool] && !d.error) addToolLine(d.tool, d.query || "");
        break;
      }

      case "note": {
        state.stats.notes += 1;
        if (d.source === "arxiv_paper_search") state.stats.arxiv += 1;
        else if (d.source === "wikipedia_search") state.stats.wiki += 1;
        else if (d.source === "web_search") state.stats.web += 1;
        updateMeta();
        addNoteCard(d);
        break;
      }

      case "eval": {
        if (ev.status === "done") setStage("evaluator", "done");
        addEvalCard(d);
        break;
      }

      case "route": {
        if (ev.message) addRouteLine(ev.message);
        break;
      }

      case "review_required": {
        setStage("reviewer", "active");
        setStatus("awaiting", "待你审阅");
        addBanner("人工审核闸门 · interrupt");
        showReview(d);
        break;
      }

      case "review_submitted": {
        hideReview();
        setStatus("running", "继续运行");
        break;
      }

      case "chunk": {
        reportChunk(d.delta || "");
        break;
      }

      case "done": {
        state.terminal = true;
        setStatus("done", "已完成");
        STAGES.forEach((s) => setStage(s.key, "done"));
        reportDone(d);
        stopClock();
        if (state.es) { state.es.close(); state.es = null; }
        refreshResumePill();
        break;
      }

      case "error": {
        state.terminal = true;
        setStatus("error", "出错");
        addErrorCard(d.message || "未知错误");
        stopClock();
        if (state.es) { state.es.close(); state.es = null; }
        refreshResumePill();
        break;
      }
    }
  }

  /* ------------------------------ HITL 审阅面板 ------------------------------ */

  function showReview(d) {
    $("#runBody").classList.add("hidden");
    const panel = $("#reviewPanel");
    panel.classList.remove("hidden");

    const roundNote = panel.querySelector(".review-round-note");
    if (roundNote) roundNote.remove();
    if ((d.round ?? 1) > 1) {
      panel.querySelector(".review-doc").insertAdjacentHTML(
        "afterbegin",
        `<div class="review-round-note">第 ${d.round} 版 · 已按你的意见修订大纲</div>`
      );
    }

    $("#reviewTopic").textContent = d.topic || state.topic;
    const notes = d.notes_count ?? 0;
    $("#reviewMeta").innerHTML = `ROUND ${d.round ?? 1}<br>${notes} 条事实笔记`;

    const outlineMd = (d.outline || "").trim();
    $("#outlineBody").innerHTML = outlineMd
      ? mdToHtml(outlineMd)
      : `<p class="outline-empty">本轮检索已达上限但未产出结构化大纲。你可以直接通过（撰写将基于事实笔记自由展开），或在右侧意见中要求先补一版大纲。</p>`;
    $("#feedbackInput").value = "";
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function hideReview() {
    $("#reviewPanel").classList.add("hidden");
    $("#runBody").classList.remove("hidden");
  }

  async function submitFeedback(feedback) {
    if (!state.sessionId) return;
    const btns = [$("#approveBtn"), $("#feedbackBtn")];
    btns.forEach((b) => (b.disabled = true));
    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId, feedback }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        addErrorCard(err.error || `提交失败 (${res.status})`);
      }
    } catch (e) {
      addErrorCard(`无法连接服务器: ${e.message}`);
    } finally {
      btns.forEach((b) => (b.disabled = false));
    }
  }

  /* ------------------------------ 研报视图 ------------------------------ */

  function reportStart() {
    hideReview();
    setStatus("running", "撰写中");
    state.writing = true;
    $("#writingBanner").classList.remove("hidden");
    $("#reportBody").classList.add("is-writing");
    $("#reportActions").classList.add("hidden");
    showView("report");
  }

  function reportChunk(delta) {
    state.streamBuf += delta;
    if (!state.streamTimer) {
      state.streamTimer = setTimeout(flushStream, 140);
    }
  }

  function flushStream() {
    state.streamTimer = 0;
    state.reportText += state.streamBuf;
    state.streamBuf = "";
    renderReport(false);
    if (!state.userScrolled) {
      window.scrollTo({ top: document.documentElement.scrollHeight });
    }
  }

  function renderReport(final) {
    const body = $("#reportBody");
    body.innerHTML = mdToHtml(state.reportText);
    if (final) {
      const first = body.firstElementChild;
      if (first && first.tagName === "H1") first.remove();
    }
  }

  function reportDone(d) {
    if (d.report) state.reportText = d.report;
    state.writing = false;
    flushNow();
    $("#reportBody").classList.remove("is-writing");
    $("#writingBanner").classList.add("hidden");
    $("#reportTitle").textContent = d.topic || state.topic;

    const date = new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
    const meta = [
      `生成于 ${date}`,
      `${(state.reportText || "").length.toLocaleString()} 字符`,
      `${d.notes_count ?? state.stats.notes} 条事实笔记`,
    ];
    const filepath = d.filepath || state.reportFilepath;
    if (filepath) meta.push(filepath);
    $("#reportMeta").innerHTML = meta.map(escapeHtml).join("<br>");
    $("#reportActions").classList.remove("hidden");
    showView("report");
  }

  function flushNow() {
    if (state.streamTimer) {
      clearTimeout(state.streamTimer);
      state.streamTimer = 0;
    }
    state.reportText += state.streamBuf;
    state.streamBuf = "";
    renderReport(true);
  }

  /* ------------------------------ 启动新调研 ------------------------------ */

  async function startResearch(topic) {
    const hint = $("#composerHint");
    hint.textContent = "";
    try {
      const res = await fetch("/api/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        hint.textContent = err.error || `启动失败 (${res.status})`;
        return;
      }
      const data = await res.json();
      enterPipeline(topic, data.session_id);
      connectSSE(data.session_id);
    } catch (e) {
      hint.textContent = "无法连接服务器，请确认已运行 python frontend/server.py";
    }
  }

  /* ------------------------------ 交互绑定 ------------------------------ */

  function bind() {
    const input = $("#topicInput");

    $("#startBtn").addEventListener("click", () => {
      const topic = input.value.trim();
      if (!topic) {
        $("#composerHint").textContent = "请先输入一个调研主题";
        input.focus();
        return;
      }
      startResearch(topic);
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") $("#startBtn").click();
    });

    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        input.value = chip.textContent.trim();
        input.focus();
      });
    });

    $("#resumePill").addEventListener("click", () => {
      if (!state.sessionId) return;
      enterPipeline(state.topic, state.sessionId);
      connectSSE(state.sessionId);
    });

    $("#brandHome").addEventListener("click", (e) => {
      e.preventDefault();
      goHome({ keepSession: !state.terminal && !!state.sessionId });
    });

    $("#backBtn").addEventListener("click", () => {
      goHome({ keepSession: !state.terminal && !!state.sessionId });
    });

    $("#approveBtn").addEventListener("click", () => {
      const text = $("#feedbackInput").value.trim();
      submitFeedback(text || APPROVE_DEFAULT);
    });

    $("#feedbackBtn").addEventListener("click", () => {
      const text = $("#feedbackInput").value.trim();
      if (!text) {
        $("#feedbackInput").focus();
        $("#feedbackInput").placeholder = "请先写下你的修改意见…";
        return;
      }
      submitFeedback(text);
    });

    $("#newBtn").addEventListener("click", () => {
      goHome();
      $("#topicInput").value = "";
      $("#topicInput").focus();
    });

    $("#downloadBtn").addEventListener("click", () => {
      const safe = (state.topic || "research").replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, "_");
      const blob = new Blob([state.reportText], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${safe}_deep_research.md`;
      a.click();
      URL.revokeObjectURL(url);
    });

    $("#copyBtn").addEventListener("click", async (e) => {
      try {
        await navigator.clipboard.writeText(state.reportText);
        const btn = e.currentTarget;
        const orig = btn.textContent;
        btn.textContent = "已复制";
        setTimeout(() => (btn.textContent = orig), 1800);
      } catch {
        $("#reportMeta").textContent = "复制失败：浏览器未授权剪贴板权限";
      }
    });

    window.addEventListener("scroll", () => {
      state.userScrolled = !nearBottom();
    }, { passive: true });
  }

  /* ------------------------------ 初始化：恢复进行中的会话 ------------------------------ */

  function restoreSession() {
    try {
      const saved = JSON.parse(sessionStorage.getItem("drs-session") || "null");
      if (saved && saved.id && saved.topic) {
        enterPipeline(saved.topic, saved.id);
        connectSSE(saved.id);
      }
    } catch {
      sessionStorage.removeItem("drs-session");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    bind();
    restoreSession();
  });
})();
