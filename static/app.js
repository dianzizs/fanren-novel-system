const bookId = document.body.dataset.bookId;
let currentChapter = 1;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const graphState = {
  canvas: null,
  ctx: null,
  nodes: [],
  edges: [],
  nodeMap: new Map(),
  selectedId: null,
  hoveredId: null,
  draggedNode: null,
  pointerOffset: { x: 0, y: 0 },
  animationFrame: null,
  dpr: window.devicePixelRatio || 1,
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[character]));
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "无效";
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function formatNumber(num) {
  if (!Number.isFinite(num) || num < 0) return "无效";
  if (num === 0) return "0";
  return num.toLocaleString();
}

function formatMultiline(value) {
  return escapeHtml(value).replace(/\n/g, "<br />");
}

function feedbackCard(title, message, tone = "neutral") {
  return `
    <div class="feedback-card ${tone}">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function setLiveStatus(message) {
  const liveRegion = $("#live-status");
  if (liveRegion) {
    liveRegion.textContent = message;
  }
}

function setWorkspaceStatus(message, tone = "ready") {
  const status = $("#workspace-status");
  if (status) {
    status.textContent = message;
    status.dataset.tone = tone;
  }
  setLiveStatus(message);
}

function setHeroBook(title) {
  const target = $("#active-book-name");
  if (target) {
    target.textContent = title || "未命名书目";
  }
}

function setHeroSubtitle(text) {
  const target = $("#hero-subtitle");
  if (target) {
    target.textContent = text;
  }
}

function setActiveChapter(chapter, title = "") {
  const target = $("#active-chapter");
  if (!target) {
    return;
  }
  target.textContent = title ? `第 ${chapter} 章 · ${title}` : `第 ${chapter} 章`;
}

function setScopeSummary(scope = currentAskScope()) {
  const target = $("#active-scope");
  if (target) {
    target.textContent = `${scope.start} - ${scope.end} 章`;
  }
}

function setButtonLoading(button, loading, loadingLabel) {
  if (!button) {
    return;
  }
  if (!button.dataset.defaultLabel) {
    button.dataset.defaultLabel = button.textContent.trim();
  }
  button.disabled = loading;
  button.classList.toggle("is-loading", loading);
  button.textContent = loading ? loadingLabel : button.dataset.defaultLabel;
}

function setRegionFeedback(target, title, message, tone = "neutral") {
  const element = typeof target === "string" ? $(target) : target;
  if (!element) {
    return;
  }
  element.innerHTML = feedbackCard(title, message, tone);
}

function handleActionError(error, target = null, title = "操作失败") {
  console.error(error);
  const message = error instanceof Error ? error.message : String(error);
  if (target) {
    setRegionFeedback(target, title, message, "error");
  }
  setWorkspaceStatus("发生错误，请查看界面提示", "warn");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function currentAskScope() {
  return {
    start: Number($("#scope-start")?.value || 1),
    end: Number($("#scope-end")?.value || 14),
  };
}

function currentGraphScope() {
  return {
    start: Number($("#graph-scope-start")?.value || 1),
    end: Number($("#graph-scope-end")?.value || 14),
  };
}

function syncGraphScopeToAsk() {
  const askScope = currentAskScope();
  if ($("#graph-scope-start")) {
    $("#graph-scope-start").value = askScope.start;
  }
  if ($("#graph-scope-end")) {
    $("#graph-scope-end").value = askScope.end;
  }
  setScopeSummary(askScope);
}

function activateTab(nextButton) {
  $$(".tab").forEach((button) => {
    const isActive = button === nextButton;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
    button.tabIndex = isActive ? 0 : -1;
  });

  $$(".tab-panel").forEach((panel) => {
    const isActive = panel.id === `tab-${nextButton.dataset.tab}`;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });

  if (nextButton.dataset.tab === "knowledge") {
    loadGraph().catch((error) => handleActionError(error, "#graph-detail", "图谱加载失败"));
  }
}

function setTabs() {
  const tabs = $$(".tab");
  tabs.forEach((button, index) => {
    button.addEventListener("click", () => activateTab(button));
    button.addEventListener("keydown", (event) => {
      let nextIndex = null;

      if (event.key === "ArrowRight") {
        nextIndex = (index + 1) % tabs.length;
      } else if (event.key === "ArrowLeft") {
        nextIndex = (index - 1 + tabs.length) % tabs.length;
      } else if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = tabs.length - 1;
      }

      if (nextIndex === null) {
        return;
      }

      event.preventDefault();
      tabs[nextIndex].focus();
      activateTab(tabs[nextIndex]);
    });
  });
}

function renderEmptyList(target, title, message) {
  const element = typeof target === "string" ? $(target) : target;
  if (!element) {
    return;
  }
  element.innerHTML = feedbackCard(title, message);
}

async function loadBooks() {
  const books = await fetchJson("/api/books");
  const bookCards = $("#book-cards");

  if (!books.length) {
    setHeroBook("暂无书目");
    setHeroSubtitle("先导入一本小说，再在这里查看索引、图谱和评测。");
    renderEmptyList(bookCards, "暂无书目", "可以先通过 API 导入一本小说，再回到工作台查看。");
    setWorkspaceStatus("书库为空，等待导入", "idle");
    return;
  }

  const activeBook = books.find((book) => String(book.id) === String(bookId)) || books[0];
  setHeroBook(activeBook.title);
  setHeroSubtitle(
    `已接入 ${activeBook.chapter_count || 0} 章、${activeBook.chunk_count || 0} 个切片，阅读、图谱、续写与评测共用同一套索引。`,
  );

  bookCards.innerHTML = books.map((book) => {
    const isActive = String(book.id) === String(bookId);
    const indexed = Boolean(book.indexed);
    const sourceTag = book.source === "upload"
      ? '<span class="source-tag upload">本地上传</span>'
      : '<span class="source-tag local">原书</span>';
    return `
      <div class="book-card ${isActive ? "active" : ""}">
        <div class="book-card-actions">
          <button class="delete-book-btn" data-book-id="${escapeHtml(book.id)}" data-book-title="${escapeHtml(book.title)}">删除</button>
        </div>
        <div class="status-row">
          <span class="status-tag ${indexed ? "" : "pending"}">${indexed ? "已索引" : "待处理"}</span>
          ${sourceTag}
          ${isActive ? "<span class='mini-tag'>当前工作本</span>" : ""}
        </div>
        <h3>${escapeHtml(book.title)}</h3>
        <div class="book-meta">ID：${escapeHtml(book.id)}</div>
        <div class="book-meta">章节数：${escapeHtml(book.chapter_count || "-")}</div>
        <div class="book-meta">切片数：${escapeHtml(book.chunk_count || "-")}</div>
        <div class="book-meta">${escapeHtml(book.source_path || "未记录来源路径")}</div>
      </div>
    `;
  }).join("");

  const indexedCount = books.filter((book) => book.indexed).length;
  setWorkspaceStatus(`书库 ${books.length} 本，已索引 ${indexedCount} 本`, indexedCount ? "ready" : "idle");
}

async function loadStorageStats() {
  try {
    const stats = await fetchJson("/api/storage-stats");
    $("#index-size").textContent = formatBytes(stats.total_index_size || 0);
    $("#uploads-size").textContent = formatBytes(stats.total_uploads_size || 0);
  } catch (error) {
    console.error("Failed to load storage stats:", error);
    $("#index-size").textContent = "加载失败";
    $("#uploads-size").textContent = "加载失败";
  }
}

async function loadTokenStats() {
  try {
    const stats = await fetchJson("/api/token-stats");
    $("#token-total").textContent = formatNumber(stats.total_tokens || 0);
  } catch (error) {
    console.error("Failed to load token stats:", error);
    $("#token-total").textContent = "加载失败";
  }
}

function showDeleteConfirmDialog(bookId, bookTitle) {
  const overlay = document.createElement("div");
  overlay.className = "confirm-dialog-overlay";
  overlay.innerHTML = `
    <div class="confirm-dialog">
      <h3>确认删除</h3>
      <p>确定删除《${escapeHtml(bookTitle)}》吗？此操作不可恢复，所有索引数据将被删除。</p>
      <div class="confirm-dialog-actions">
        <button class="secondary" id="cancel-delete-btn">取消</button>
        <button class="primary" id="confirm-delete-btn" data-book-id="${escapeHtml(bookId)}">确认删除</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  $("#cancel-delete-btn").addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  $("#confirm-delete-btn").addEventListener("click", async () => {
    const btn = $("#confirm-delete-btn");
    btn.disabled = true;
    btn.textContent = "删除中...";
    try {
      await fetchJson(`/api/books/${btn.dataset.bookId}`, { method: "DELETE" });
      overlay.remove();
      await loadBooks();
      await loadStorageStats();
      setWorkspaceStatus("书目已删除", "ready");
    } catch (error) {
      handleActionError(error, null, "删除失败");
      btn.disabled = false;
      btn.textContent = "确认删除";
    }
  });
}

async function loadReader(chapter = 1) {
  const payload = await fetchJson(`/api/books/${bookId}/reader?chapter=${chapter}`);
  const chapters = payload.chapters || [];
  const current = payload.current_chapter || {};
  const summary = chapters.find((item) => item.chapter === current.chapter)?.summary || "暂无摘要。";
  currentChapter = current.chapter || chapter;

  setActiveChapter(currentChapter, current.title || "");

  $("#reader-summary").innerHTML = `
    <strong>第 ${escapeHtml(currentChapter)} 章 · ${escapeHtml(current.title || "未命名章节")}</strong>
    <p>${escapeHtml(summary)}</p>
  `;

  $("#reader-content").textContent = current.text || "暂无正文。";

  if (!chapters.length) {
    renderEmptyList("#chapter-tree", "暂无章节", "索引完成后，这里会显示章节目录。");
  } else {
    $("#chapter-tree").innerHTML = chapters.map((chapterItem) => `
      <div
        class="chapter-item ${chapterItem.chapter === currentChapter ? "active" : ""}"
        data-chapter="${escapeHtml(chapterItem.chapter)}"
        tabindex="0"
      >
        <strong>第 ${escapeHtml(chapterItem.chapter)} 章</strong>
        <span>${escapeHtml(chapterItem.title || "未命名章节")}</span>
      </div>
    `).join("");
  }

  const topCharacters = payload.top_characters || [];
  if (!topCharacters.length) {
    renderEmptyList("#character-cards", "暂无人物卡", "读取章节后，这里会展示当前范围内的重要人物。");
  } else {
    $("#character-cards").innerHTML = topCharacters.map((character) => `
      <div class="character-card">
        <strong>${escapeHtml(character.title)}</strong>
        <p>${escapeHtml(character.text)}</p>
      </div>
    `).join("");
  }

  const timeline = payload.timeline || [];
  if (!timeline.length) {
    renderEmptyList("#timeline-board", "暂无时间线", "索引结果会在这里聚合出主要事件。");
  } else {
    $("#timeline-board").innerHTML = timeline.map((event) => `
      <div class="timeline-card">
        <strong>第 ${escapeHtml(event.chapter)} 章 · ${escapeHtml(event.title)}</strong>
        <p>${escapeHtml(event.description)}</p>
      </div>
    `).join("");
  }

  $$(".chapter-item").forEach((item) => {
    const openChapter = () => loadReader(Number(item.dataset.chapter)).catch((error) => {
      handleActionError(error, "#reader-summary", "章节加载失败");
    });
    item.addEventListener("click", openChapter);
    item.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openChapter();
      }
    });
  });
}

async function askQuestion() {
  const query = $("#ask-query").value.trim();
  const button = $("#ask-btn");

  if (!query) {
    setRegionFeedback("#ask-result", "还没有问题", "先输入一个问题，再开始检索证据。");
    setWorkspaceStatus("等待输入问题", "idle");
    return;
  }

  const scope = currentAskScope();
  const payload = {
    user_query: query,
    scope: { chapters: [scope.start, scope.end] },
    conversation_history: [
      { role: "user", content: "之后回答尽量简洁一点，但要带证据。" },
    ],
    session_id: "workspace",
  };

  setButtonLoading(button, true, "检索中...");
  setRegionFeedback("#ask-result", "正在分析", "正在检索相关片段并组织答案。");
  setWorkspaceStatus("正在生成证据回答", "busy");

  try {
    const result = await fetchJson(`/api/books/${bookId}/ask`, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    $("#ask-result").innerHTML = `
      <strong>回答</strong>
      <p>${formatMultiline(result.answer || "暂无回答。")}</p>
      <div class="answer-meta">
        任务类型：${escapeHtml(result.planner?.task_type || "-")} · 不确定性：${escapeHtml(result.uncertainty ?? "-")}
      </div>
    `;

    const evidence = result.evidence || [];
    if (!evidence.length) {
      renderEmptyList("#evidence-list", "暂无证据", "这次回答没有返回可展示的引用片段。");
    } else {
      $("#evidence-list").innerHTML = evidence.map((item) => `
        <div class="evidence-card">
          <strong>第 ${escapeHtml(item.chapter)} 章 · ${escapeHtml(item.target)}</strong>
          <p>${escapeHtml(item.quote)}</p>
          <div class="book-meta">${escapeHtml(item.source || "未标注来源")}</div>
        </div>
      `).join("");
    }

    setWorkspaceStatus("证据回答已更新", "ready");
    loadTokenStats().catch(console.error);
  } catch (error) {
    handleActionError(error, "#ask-result", "问答生成失败");
  } finally {
    setButtonLoading(button, false, "检索中...");
  }
}

async function continueStory() {
  const query = $("#continuation-query").value.trim();
  const button = $("#continue-btn");

  if (!query) {
    setRegionFeedback("#continuation-result", "还没有指令", "先写下续写约束或创作方向。");
    setWorkspaceStatus("等待续写指令", "idle");
    return;
  }

  const scope = currentAskScope();
  const payload = {
    user_query: query,
    scope: { chapters: [scope.start, scope.end] },
    conversation_history: [
      { role: "user", content: "只看前 14 章，不要剧透后面。" },
    ],
    session_id: "workspace",
  };

  setButtonLoading(button, true, "生成中...");
  $("#continuation-result").textContent = "正在生成续写...";
  setWorkspaceStatus("正在生成续写", "busy");

  try {
    const result = await fetchJson(`/api/books/${bookId}/continue`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("#continuation-result").textContent = result.answer || "暂无结果。";
    setWorkspaceStatus("续写结果已更新", "ready");
    loadTokenStats().catch(console.error);
  } catch (error) {
    handleActionError(error, "#continuation-result", "续写生成失败");
  } finally {
    setButtonLoading(button, false, "生成中...");
  }
}

async function loadDashboard() {
  const dashboard = await fetchJson("/api/dashboard");
  const metrics = dashboard.metrics || [];
  const baseline = dashboard.baseline_comparison || [];
  const failures = dashboard.failures || [];

  if (!metrics.length) {
    renderEmptyList("#metric-grid", "暂无指标", "运行评测脚本后，这里会显示核心指标。");
  } else {
    $("#metric-grid").innerHTML = metrics.map((item) => `
      <div class="metric-card">
        <strong>${escapeHtml(item.name)}</strong>
        <div class="metric-value">${escapeHtml(item.value ?? "--")}</div>
        <div class="metric-note">${escapeHtml(item.note ?? "")}</div>
      </div>
    `).join("");
  }

  $("#baseline-list").innerHTML = baseline.length
    ? baseline.map((item) => `
      <div class="baseline-item">
        <strong>${escapeHtml(item.system)}</strong>
        <p>得分：${escapeHtml(item.score)}</p>
      </div>
    `).join("")
    : feedbackCard("暂无基线对比", "当前还没有可展示的 baseline 结果。");

  $("#failure-list").innerHTML = failures.length
    ? failures.map((item) => `
      <div class="failure-card">
        <strong>${escapeHtml(item.id)}</strong>
        <p>类别：${escapeHtml(item.category)}</p>
        <p>得分：${escapeHtml(item.score)}</p>
      </div>
    `).join("")
    : feedbackCard("暂无失败案例", "评测运行后，如果有失败样例会显示在这里。");

  $("#chart-json").textContent = JSON.stringify(dashboard.charts || {}, null, 2);
}

async function rebuildIndex() {
  const button = $("#index-book-btn");
  setButtonLoading(button, true, "构建中...");
  setWorkspaceStatus("正在重建索引", "busy");

  try {
    await fetchJson(`/api/books/${bookId}/index`, { method: "POST" });
    await loadBooks();
    await loadReader(currentChapter);
    await loadDashboard();
    await loadGraph();
    setWorkspaceStatus("索引已重建", "ready");
  } catch (error) {
    handleActionError(error, "#book-cards", "索引重建失败");
  } finally {
    setButtonLoading(button, false, "构建中...");
  }
}

async function refreshWorkspace() {
  const button = $("#reload-dashboard-btn");
  setButtonLoading(button, true, "同步中...");
  setWorkspaceStatus("正在同步看板", "busy");

  try {
    await loadBooks();
    await loadReader(currentChapter);
    await loadDashboard();
    await loadGraph();
    setWorkspaceStatus("看板已同步", "ready");
  } catch (error) {
    handleActionError(error, "#metric-grid", "看板同步失败");
  } finally {
    setButtonLoading(button, false, "同步中...");
  }
}

function populateGraphCharacterOptions(characters, selected) {
  const select = $("#graph-center");
  if (!select) {
    return;
  }

  const current = selected ?? select.value;
  select.innerHTML = "";

  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "自动选择";
  select.appendChild(defaultOption);

  characters.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    if (name === current) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

async function loadGraph() {
  const scope = currentGraphScope();
  const center = $("#graph-center")?.value || "";
  const query = new URLSearchParams({
    chapter_start: String(scope.start),
    chapter_end: String(scope.end),
    limit: "20",
  });

  if (center) {
    query.set("center", center);
  }

  const payload = await fetchJson(`/api/books/${bookId}/graph?${query.toString()}`);
  populateGraphCharacterOptions(payload.available_characters || [], payload.center || center);
  renderGraph(payload);
}

function setupGraphCanvas() {
  const canvas = $("#knowledge-graph-canvas");
  if (!canvas) {
    return;
  }

  graphState.canvas = canvas;
  graphState.ctx = canvas.getContext("2d");
  resizeGraphCanvas();
  canvas.addEventListener("mousedown", onGraphPointerDown);
  canvas.addEventListener("mousemove", onGraphPointerMove);
  window.addEventListener("mouseup", onGraphPointerUp);
  canvas.addEventListener("mouseleave", onGraphPointerUp);
  window.addEventListener("resize", () => {
    resizeGraphCanvas();
    drawGraph();
  });
}

function resizeGraphCanvas() {
  if (!graphState.canvas || !graphState.ctx) {
    return;
  }

  const rect = graphState.canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  graphState.dpr = dpr;
  graphState.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  graphState.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  graphState.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function renderGraph(payload) {
  const previousPositions = new Map(graphState.nodes.map((node) => [node.id, { x: node.x, y: node.y }]));
  graphState.nodes = (payload.nodes || []).map((node, index) => {
    const prev = previousPositions.get(node.id);
    const width = graphState.canvas?.clientWidth || 900;
    const height = graphState.canvas?.clientHeight || 500;
    return {
      ...node,
      radius: node.size,
      x: prev?.x ?? 90 + (index % 6) * 120 + Math.random() * 24,
      y: prev?.y ?? 80 + Math.floor(index / 6) * 92 + Math.random() * 24,
      vx: 0,
      vy: 0,
      fx: null,
      fy: null,
      boundsWidth: width,
      boundsHeight: height,
    };
  });

  graphState.nodeMap = new Map(graphState.nodes.map((node) => [node.id, node]));
  graphState.edges = (payload.edges || [])
    .map((edge) => ({
      ...edge,
      sourceNode: graphState.nodeMap.get(edge.source),
      targetNode: graphState.nodeMap.get(edge.target),
    }))
    .filter((edge) => edge.sourceNode && edge.targetNode);

  graphState.selectedId = payload.center ? `char::${payload.center}` : graphState.nodes[0]?.id || null;
  updateGraphDetail(graphState.nodeMap.get(graphState.selectedId), payload.stats || null);
  startGraphLoop();
}

function startGraphLoop() {
  if (graphState.animationFrame) {
    cancelAnimationFrame(graphState.animationFrame);
  }

  const frame = () => {
    stepGraphSimulation();
    drawGraph();
    graphState.animationFrame = requestAnimationFrame(frame);
  };

  graphState.animationFrame = requestAnimationFrame(frame);
}

function stepGraphSimulation() {
  const width = graphState.canvas?.clientWidth || 900;
  const height = graphState.canvas?.clientHeight || 500;
  const centerX = width / 2;
  const centerY = height / 2;
  const nodes = graphState.nodes;

  for (let index = 0; index < nodes.length; index += 1) {
    const node = nodes[index];
    for (let inner = index + 1; inner < nodes.length; inner += 1) {
      const other = nodes[inner];
      let dx = node.x - other.x;
      let dy = node.y - other.y;
      let distanceSq = dx * dx + dy * dy;

      if (distanceSq < 1) {
        distanceSq = 1;
        dx = 1;
        dy = 0;
      }

      const force = 2200 / distanceSq;
      node.vx += (dx * force) / 80;
      node.vy += (dy * force) / 80;
      other.vx -= (dx * force) / 80;
      other.vy -= (dy * force) / 80;
    }
  }

  graphState.edges.forEach((edge) => {
    const source = edge.sourceNode;
    const target = edge.targetNode;
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy));
    const desired = edge.type === "character_relation"
      ? 132
      : edge.type === "participates_in"
        ? 96
        : 162;
    const strength = 0.004 + Math.min(edge.weight, 8) * 0.0009;
    const spring = (distance - desired) * strength;
    const nx = dx / distance;
    const ny = dy / distance;
    source.vx += nx * spring;
    source.vy += ny * spring;
    target.vx -= nx * spring;
    target.vy -= ny * spring;
  });

  nodes.forEach((node) => {
    const attraction = node.type === "character" ? 0.0015 : 0.001;
    node.vx += (centerX - node.x) * attraction;
    node.vy += (centerY - node.y) * attraction;

    if (graphState.draggedNode?.id === node.id) {
      node.vx = 0;
      node.vy = 0;
      return;
    }

    node.vx *= 0.88;
    node.vy *= 0.88;
    node.x += node.vx;
    node.y += node.vy;
    node.x = Math.max(30, Math.min(width - 30, node.x));
    node.y = Math.max(30, Math.min(height - 30, node.y));
  });
}

function graphNodeColor(node) {
  if (node.is_center) {
    return "#ff7e8b";
  }
  return node.type === "character" ? "#74e1b8" : "#f5c96a";
}

function edgeColor(edge) {
  if (edge.type === "timeline_next") {
    return "rgba(245, 201, 106, 0.24)";
  }
  if (edge.type === "participates_in") {
    return "rgba(255, 126, 139, 0.26)";
  }
  return "rgba(116, 225, 184, 0.36)";
}

function truncateLabel(label, maxLength = 12) {
  const text = String(label || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function drawGraph() {
  if (!graphState.ctx || !graphState.canvas) {
    return;
  }

  const ctx = graphState.ctx;
  const width = graphState.canvas.clientWidth;
  const height = graphState.canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);

  graphState.edges.forEach((edge) => {
    const { sourceNode, targetNode } = edge;
    ctx.beginPath();
    ctx.moveTo(sourceNode.x, sourceNode.y);
    ctx.lineTo(targetNode.x, targetNode.y);
    ctx.strokeStyle = edgeColor(edge);
    ctx.lineWidth = edge.type === "character_relation" ? 1.9 : 1.2;
    ctx.stroke();
  });

  graphState.nodes.forEach((node) => {
    const isSelected = graphState.selectedId === node.id;
    const isHovered = graphState.hoveredId === node.id;

    ctx.save();
    ctx.beginPath();
    ctx.fillStyle = graphNodeColor(node);
    ctx.shadowBlur = isSelected ? 18 : isHovered ? 12 : 0;
    ctx.shadowColor = isSelected ? "rgba(255, 126, 139, 0.42)" : "rgba(116, 225, 184, 0.28)";
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.beginPath();
    ctx.lineWidth = isSelected || isHovered ? 3 : 1.5;
    ctx.strokeStyle = isSelected || isHovered ? "#f7f5ef" : "rgba(255, 255, 255, 0.65)";
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.stroke();

    ctx.font = node.type === "event"
      ? '600 12px "Noto Sans SC", sans-serif'
      : '600 13px "Noto Sans SC", sans-serif';
    ctx.fillStyle = "rgba(243, 244, 239, 0.92)";
    ctx.textAlign = "center";
    ctx.fillText(truncateLabel(node.label), node.x, node.y + node.radius + 16);
  });
}

function graphPointerPosition(event) {
  const rect = graphState.canvas.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

function findGraphNodeAt(x, y) {
  for (let index = graphState.nodes.length - 1; index >= 0; index -= 1) {
    const node = graphState.nodes[index];
    const dx = x - node.x;
    const dy = y - node.y;
    if (Math.sqrt(dx * dx + dy * dy) <= node.radius + 4) {
      return node;
    }
  }
  return null;
}

function onGraphPointerDown(event) {
  if (!graphState.canvas) {
    return;
  }

  const { x, y } = graphPointerPosition(event);
  const node = findGraphNodeAt(x, y);
  if (!node) {
    return;
  }

  graphState.draggedNode = node;
  graphState.selectedId = node.id;
  graphState.pointerOffset = { x: x - node.x, y: y - node.y };
  updateGraphDetail(node);
}

function onGraphPointerMove(event) {
  if (!graphState.canvas) {
    return;
  }

  const { x, y } = graphPointerPosition(event);
  const hovered = findGraphNodeAt(x, y);
  graphState.hoveredId = hovered?.id || null;
  graphState.canvas.style.cursor = hovered ? "pointer" : "default";

  if (graphState.draggedNode) {
    graphState.draggedNode.x = x - graphState.pointerOffset.x;
    graphState.draggedNode.y = y - graphState.pointerOffset.y;
    graphState.draggedNode.vx = 0;
    graphState.draggedNode.vy = 0;
  }
}

function onGraphPointerUp() {
  graphState.draggedNode = null;
}

function updateGraphDetail(node, stats = null) {
  const detail = $("#graph-detail");
  if (!detail) {
    return;
  }

  if (!node) {
    detail.innerHTML = `
      <h3>节点详情</h3>
      <p>点击节点查看摘要、章节范围和连接关系。</p>
    `;
    return;
  }

  const related = graphState.edges
    .filter((edge) => edge.source === node.id || edge.target === node.id)
    .slice(0, 8)
    .map((edge) => {
      const otherId = edge.source === node.id ? edge.target : edge.source;
      const other = graphState.nodeMap.get(otherId);
      return `${escapeHtml(other?.label || otherId)} · ${escapeHtml(edge.label || edge.type)}`;
    });

  const chips = node.type === "character"
    ? (node.aliases || []).concat((node.chapters || []).map((chapter) => `第 ${chapter} 章`))
    : (node.participants || []);

  const statsLine = stats
    ? `<div class="graph-meta">节点 ${escapeHtml((stats.character_count || 0) + (stats.event_count || 0))} · 边 ${escapeHtml(stats.edge_count || 0)}</div>`
    : "";

  detail.innerHTML = `
    <h3>${escapeHtml(node.label)}</h3>
    <div class="graph-meta">类型：${escapeHtml(node.type)} · 章节：${escapeHtml(node.chapter ?? "-")}</div>
    <p>${escapeHtml(node.summary || "暂无摘要。")}</p>
    ${statsLine}
    <h4>标签</h4>
    <div class="graph-chip-row">
      ${(chips || []).slice(0, 10).map((item) => `<span class="graph-chip">${escapeHtml(item)}</span>`).join("") || "<span class='graph-chip'>暂无标签</span>"}
    </div>
    <h4>连接</h4>
    <p>${related.join("<br />") || "当前范围内没有可展示的连接。"}</p>
  `;
}

function bindEvents() {
  $("#ask-btn").addEventListener("click", askQuestion);
  $("#continue-btn").addEventListener("click", continueStory);
  $("#reload-dashboard-btn").addEventListener("click", refreshWorkspace);
  $("#index-book-btn").addEventListener("click", rebuildIndex);
  $("#refresh-graph-btn")?.addEventListener("click", () => {
    setWorkspaceStatus("正在刷新图谱", "busy");
    loadGraph()
      .then(() => setWorkspaceStatus("图谱已刷新", "ready"))
      .catch((error) => handleActionError(error, "#graph-detail", "图谱加载失败"));
  });
  $("#graph-center")?.addEventListener("change", () => {
    loadGraph().catch((error) => handleActionError(error, "#graph-detail", "图谱加载失败"));
  });
  $("#scope-start")?.addEventListener("change", syncGraphScopeToAsk);
  $("#scope-end")?.addEventListener("change", syncGraphScopeToAsk);

  // 删除按钮事件
  document.addEventListener("click", (e) => {
    if (e.target.classList.contains("delete-book-btn")) {
      const btn = e.target;
      showDeleteConfirmDialog(btn.dataset.bookId, btn.dataset.bookTitle);
    }
  });

  // 刷新书库按钮
  $("#refresh-books-btn")?.addEventListener("click", async () => {
    const btn = $("#refresh-books-btn");
    setButtonLoading(btn, true, "刷新中...");
    try {
      await loadBooks();
      await loadStorageStats();
      setWorkspaceStatus("书库已刷新", "ready");
    } catch (error) {
      handleActionError(error, "#book-cards", "刷新失败");
    } finally {
      setButtonLoading(btn, false, "刷新中...");
    }
  });

  // 导入新书按钮
  $("#import-book-btn")?.addEventListener("click", () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".txt";
    input.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const formData = new FormData();
      formData.append("file", file);
      try {
        const response = await fetch("/api/books", { method: "POST", body: formData });
        if (response.ok) {
          await loadBooks();
          await loadStorageStats();
          setWorkspaceStatus("新书已导入", "ready");
        }
      } catch (error) {
        handleActionError(error, "#book-cards", "导入失败");
      }
    });
    input.click();
  });
}

async function bootstrap() {
  setTabs();
  setupGraphCanvas();
  bindEvents();
  syncGraphScopeToAsk();

  try {
    await loadBooks();
    await loadStorageStats();
    await loadTokenStats();
    await loadReader(1);
    await loadDashboard();
    await loadGraph();
    setWorkspaceStatus("工作区已就绪", "ready");
  } catch (error) {
    handleActionError(error, "#book-cards", "初始化失败");
  }
}

bootstrap();
