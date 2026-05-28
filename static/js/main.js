/**
 * 主入口模块 — 统一调度所有子模块
 */

import { $, $$, setWorkspaceStatus, setButtonLoading, handleActionError } from "./utils.js";
import { initLibrary, loadBooks, rebuildIndex, loadStorageStatsUI, loadTokenStatsUI } from "./library.js";
import { initReader, loadReader } from "./reader.js";
import { initGraph, loadGraph, resizeGraphCanvas } from "./graph.js";
import { initContinuation } from "./continuation.js";
import { initEvaluation, loadDashboard } from "./evaluation.js";
import { getBooks, getBookStatus, getGraphData, getArtifacts, getArtifact } from "./api.js";

/* ── 全局状态 ── */
const appState = {
  bookId: document.body.dataset.bookId || "",
  currentChapter: 1,
  activeTab: "library",
  globalLoading: false,
  navigate(path) {
    window.location.hash = path;
  },
  onIndexComplete: async () => {
    await loadReader(appState, appState.currentChapter);
    await loadDashboard();
    await loadGraph(appState);
  },
};

/* ── Tab 切换 ── */
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

  appState.activeTab = nextButton.dataset.tab;

  if (nextButton.dataset.tab === "knowledge") {
    requestAnimationFrame(() => {
      resizeGraphCanvas();
      loadGraph(appState).catch((error) =>
        handleActionError(error, "#graph-detail", "图谱加载失败")
      );
    });
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
      if (nextIndex === null) return;
      event.preventDefault();
      tabs[nextIndex].focus();
      activateTab(tabs[nextIndex]);
    });
  });
}

/* ── 路由 ── */
const router = { currentView: "library", currentBookId: null };

const detailArtifactState = {
  bookId: null,
  selectedName: "manifest",
  catalog: [],
};

function initRouter() {
  window.addEventListener("hashchange", handleRouteChange);
  handleRouteChange();
}

function handleRouteChange() {
  const hash = window.location.hash || "#/";
  if (hash.startsWith("#/book/")) {
    const rawBookId = hash.replace("#/book/", "");
    let bookId = rawBookId;
    try {
      bookId = decodeURIComponent(rawBookId);
    } catch (error) {
      console.warn("Failed to decode book id from hash:", rawBookId, error);
    }
    router.currentView = "detail";
    router.currentBookId = bookId;
    showBookDetail(bookId);
  } else {
    router.currentView = "library";
    router.currentBookId = null;
    showLibraryView();
  }
}

function showLibraryView() {
  $("#book-detail-view").hidden = true;
  $(".tab-bar").hidden = false;
  detailArtifactState.bookId = null;
  stopPollingStatus();
}

async function showBookDetail(bookId) {
  $("#book-detail-view").hidden = false;
  $(".tab-bar").hidden = true;
  detailArtifactState.bookId = bookId;

  const books = await getBooks();
  const book = books.find((b) => b.id === bookId);
  loadDetailArtifacts(bookId).catch((error) =>
    handleActionError(error, "#detail-artifact-summary", "产物加载失败")
  );

  if (book) {
    $("#detail-book-title").textContent = `《${book.title}》`;
    updateDetailStatus(book.status || "pending", 0);
  }

  if (book && book.status === "ready") {
    $("#detail-progress").hidden = true;
    $("#detail-content").hidden = false;
    await loadDetailGraph(bookId);
  } else if (book && book.status === "indexing") {
    startPollingStatus(bookId);
  } else {
    $("#detail-progress").hidden = true;
    $("#detail-content").hidden = true;
  }

  $("#back-to-library").onclick = () => appState.navigate("#/");
}

function updateDetailStatus(status, progress, message = null) {
  const statusEl = $("#detail-book-status");
  const progressEl = $("#detail-progress");
  const fillEl = $("#progress-fill");
  const msgEl = $("#progress-message");

  statusEl.textContent = {
    pending: "等待分析",
    indexing: "分析中",
    ready: "已就绪",
    error: "分析失败",
  }[status] || status;

  if (status === "indexing") {
    progressEl.hidden = false;
    fillEl.style.width = `${(progress * 100).toFixed(0)}%`;
    msgEl.textContent = message || `正在分析... (${(progress * 100).toFixed(0)}%)`;
  } else if (status === "ready") {
    progressEl.hidden = true;
  }
}

let pollingTimer = null;

function startPollingStatus(bookId) {
  $("#detail-progress").hidden = false;
  $("#detail-content").hidden = true;

  const poll = async () => {
    const status = await getBookStatus(bookId);
    updateDetailStatus(status.status, status.progress, status.message);
    loadDetailArtifacts(bookId).catch(console.error);

    if (status.status === "indexing") {
      pollingTimer = setTimeout(poll, 2000);
    } else if (status.status === "ready") {
      $("#detail-progress").hidden = true;
      $("#detail-content").hidden = false;
      await loadDetailGraph(bookId);
      await loadDetailArtifacts(bookId);
    }
  };
  poll();
}

function stopPollingStatus() {
  if (pollingTimer) {
    clearTimeout(pollingTimer);
    pollingTimer = null;
  }
}

/* ── 详情页图谱 ── */
const detailGraphState = {
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

async function loadDetailGraph(bookId) {
  const scopeStart = parseInt($("#detail-graph-scope-start")?.value) || 1;
  const scopeEnd = parseInt($("#detail-graph-scope-end")?.value) || 14;
  const density = $("#detail-graph-density")?.value || "auto";

  try {
    const data = await getGraphData(bookId, {
      chapter_start: scopeStart,
      chapter_end: scopeEnd,
      density: density,
    });
    renderDetailForceGraph(data);
    const events = (data.nodes || [])
      .filter((n) => n.type === "event")
      .map((e) => ({ chapter: e.chapter, description: e.summary || "" }));
    renderCharacterCards(data.available_characters || [], data);
    renderDetailTimeline(events);
  } catch (error) {
    console.error("Failed to load graph:", error);
  }
}

function renderDetailForceGraph(data) {
  const canvas = $("#detail-knowledge-graph-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  detailGraphState.canvas = canvas;
  detailGraphState.ctx = ctx;

  const dpr = window.devicePixelRatio || 1;
  detailGraphState.dpr = dpr;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const width = rect.width || 600;
  const height = rect.height || 400;

  detailGraphState.nodes = (data.nodes || []).map((node, index) => ({
    ...node,
    radius: node.size,
    x: width * 0.15 + (index % 5) * (width * 0.15) + Math.random() * 20,
    y: height * 0.15 + Math.floor(index / 5) * (height * 0.15) + Math.random() * 20,
    vx: 0,
    vy: 0,
  }));

  detailGraphState.nodeMap = new Map(detailGraphState.nodes.map((n) => [n.id, n]));
  detailGraphState.edges = (data.edges || [])
    .map((edge) => ({
      ...edge,
      sourceNode: detailGraphState.nodeMap.get(edge.source),
      targetNode: detailGraphState.nodeMap.get(edge.target),
    }))
    .filter((edge) => edge.sourceNode && edge.targetNode);

  detailGraphState.selectedId = data.center
    ? `char::${data.center}`
    : detailGraphState.nodes[0]?.id || null;

  canvas.onmousedown = (e) => {
    const pos = detailGraphPointerPos(e);
    const node = detailGraphFindNode(pos.x, pos.y);
    if (node) {
      detailGraphState.draggedNode = node;
      detailGraphState.selectedId = node.id;
      detailGraphState.pointerOffset = { x: pos.x - node.x, y: pos.y - node.y };
    }
  };
  canvas.onmousemove = (e) => {
    const pos = detailGraphPointerPos(e);
    const hovered = detailGraphFindNode(pos.x, pos.y);
    detailGraphState.hoveredId = hovered?.id || null;
    canvas.style.cursor = hovered ? "pointer" : "default";
    if (detailGraphState.draggedNode) {
      detailGraphState.draggedNode.x = pos.x - detailGraphState.pointerOffset.x;
      detailGraphState.draggedNode.y = pos.y - detailGraphState.pointerOffset.y;
      detailGraphState.draggedNode.vx = 0;
      detailGraphState.draggedNode.vy = 0;
    }
  };
  canvas.onmouseup = () => { detailGraphState.draggedNode = null; };
  canvas.onmouseleave = () => {
    detailGraphState.draggedNode = null;
    detailGraphState.hoveredId = null;
  };

  detailGraphLoop();
}

function detailGraphPointerPos(e) {
  const rect = detailGraphState.canvas.getBoundingClientRect();
  return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

function detailGraphFindNode(x, y) {
  for (let i = detailGraphState.nodes.length - 1; i >= 0; i--) {
    const n = detailGraphState.nodes[i];
    const dx = x - n.x, dy = y - n.y;
    if (Math.sqrt(dx * dx + dy * dy) <= n.radius + 4) return n;
  }
  return null;
}

function detailGraphLoop() {
  if (detailGraphState.animationFrame) cancelAnimationFrame(detailGraphState.animationFrame);
  const frame = () => {
    detailGraphStepSim();
    detailGraphDraw();
    detailGraphState.animationFrame = requestAnimationFrame(frame);
  };
  detailGraphState.animationFrame = requestAnimationFrame(frame);
}

function detailGraphStepSim() {
  const canvas = detailGraphState.canvas;
  const width = canvas?.clientWidth || 600;
  const height = canvas?.clientHeight || 400;
  const cx = width / 2, cy = height / 2;
  const nodes = detailGraphState.nodes;

  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      let dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
      let dSq = dx * dx + dy * dy;
      if (dSq < 1) { dSq = 1; dx = 1; dy = 0; }
      const f = 2200 / dSq;
      nodes[i].vx += (dx * f) / 80;
      nodes[i].vy += (dy * f) / 80;
      nodes[j].vx -= (dx * f) / 80;
      nodes[j].vy -= (dy * f) / 80;
    }
  }

  detailGraphState.edges.forEach((edge) => {
    const s = edge.sourceNode, t = edge.targetNode;
    const dx = t.x - s.x, dy = t.y - s.y;
    const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
    const desired = edge.type === "character_relation" ? 132 : edge.type === "participates_in" ? 96 : 162;
    const strength = 0.004 + Math.min(edge.weight, 8) * 0.0009;
    const spring = (dist - desired) * strength;
    const nx = dx / dist, ny = dy / dist;
    s.vx += nx * spring; s.vy += ny * spring;
    t.vx -= nx * spring; t.vy -= ny * spring;
  });

  nodes.forEach((node) => {
    const attr = node.type === "character" ? 0.0015 : 0.001;
    node.vx += (cx - node.x) * attr;
    node.vy += (cy - node.y) * attr;
    if (detailGraphState.draggedNode?.id === node.id) { node.vx = 0; node.vy = 0; return; }
    node.vx *= 0.88; node.vy *= 0.88;
    node.x += node.vx; node.y += node.vy;
    node.x = Math.max(30, Math.min(width - 30, node.x));
    node.y = Math.max(30, Math.min(height - 30, node.y));
  });
}

function detailGraphDraw() {
  const ctx = detailGraphState.ctx;
  const canvas = detailGraphState.canvas;
  if (!ctx || !canvas) return;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);

  detailGraphState.edges.forEach((edge) => {
    ctx.beginPath();
    ctx.moveTo(edge.sourceNode.x, edge.sourceNode.y);
    ctx.lineTo(edge.targetNode.x, edge.targetNode.y);
    ctx.strokeStyle = edge.type === "timeline_next"
      ? "rgba(245, 158, 11, 0.24)"
      : edge.type === "participates_in"
        ? "rgba(37, 99, 235, 0.26)"
        : "rgba(14, 165, 233, 0.36)";
    ctx.lineWidth = edge.type === "character_relation" ? 1.9 : 1.2;
    ctx.stroke();
  });

  detailGraphState.nodes.forEach((node, index) => {
    const isSel = detailGraphState.selectedId === node.id;
    const isHov = detailGraphState.hoveredId === node.id;

    ctx.save();
    ctx.beginPath();
    ctx.fillStyle = node.is_center ? "#2563eb" : node.type === "character" ? "#0ea5e9" : "#f59e0b";
    ctx.shadowBlur = isSel ? 18 : isHov ? 12 : 0;
    ctx.shadowColor = isSel ? "rgba(37, 99, 235, 0.42)" : "rgba(14, 165, 233, 0.28)";
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.beginPath();
    ctx.lineWidth = isSel || isHov ? 3 : 1.5;
    ctx.strokeStyle = isSel || isHov ? "#2563eb" : "#cbd5e1";
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.stroke();

    if (shouldDrawDetailLabel(node, index)) {
      ctx.font = node.type === "event"
        ? '600 11px "Noto Sans SC", sans-serif'
        : '600 12px "Noto Sans SC", sans-serif';
      ctx.fillStyle = "#0f172a";
      ctx.textAlign = "center";
      ctx.fillText(truncateLabel(node.label), node.x, node.y + node.radius + 14);
    }
  });
}

function shouldDrawDetailLabel(node, index) {
  const total = detailGraphState.nodes.length;
  if (total <= 35) return true;
  if (detailGraphState.selectedId === node.id || detailGraphState.hoveredId === node.id) return true;
  if (node.is_center) return true;
  if (node.type === "character" && index < 18) return true;
  if (node.type === "event" && index < 8) return true;
  return false;
}

function truncateLabel(label, maxLength = 12) {
  const text = String(label || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function renderCharacterCards(characters, graphData) {
  const container = $("#detail-character-cards");
  if (!container) return;
  const charNodes = (graphData?.nodes || []).filter((n) => n.type === "character");
  const nodeMap = new Map(charNodes.map((n) => [n.label, n]));

  container.innerHTML = characters.map((name) => {
    const node = nodeMap.get(name);
    const summary = node?.summary || "";
    const chapters = node?.chapters || [];
    return `
      <div class="character-card">
        <strong>${escapeHtml(name)}</strong>
        ${chapters.length ? `<div class="book-meta">章节：${chapters.slice(0, 6).join("、")}</div>` : ""}
        ${summary ? `<p>${escapeHtml(summary)}</p>` : ""}
      </div>
    `;
  }).join("");
}

function renderDetailTimeline(events) {
  const container = $("#detail-timeline");
  if (!container) return;
  container.innerHTML = events.map((evt) => `
    <div class="timeline-card">
      <strong>第${evt.chapter}章</strong>
      <p>${escapeHtml(evt.description)}</p>
    </div>
  `).join("");
}

/* ── 详情页产物 ── */
function renderDetailArtifactCatalog() {
  const select = $("#detail-artifact-select");
  const summary = $("#detail-artifact-summary");
  if (!select || !summary) return;

  const artifacts = detailArtifactState.catalog || [];
  if (!artifacts.length) {
    select.innerHTML = "";
    summary.innerHTML = "<span class='detail-artifact-chip'>暂无可查看产物</span>";
    return;
  }

  select.innerHTML = artifacts.map((artifact) => {
    const countLabel = artifact.count == null ? "" : ` (${formatNumber(artifact.count)})`;
    const selected = artifact.name === detailArtifactState.selectedName ? " selected" : "";
    return `<option value="${escapeHtml(artifact.name)}"${selected}>${escapeHtml(artifact.label)}${escapeHtml(countLabel)}</option>`;
  }).join("");

  summary.innerHTML = artifacts.map((artifact) => {
    const countLabel = artifact.count == null ? "" : ` ${formatNumber(artifact.count)} 条`;
    const active = artifact.name === detailArtifactState.selectedName ? " active" : "";
    return `<span class="detail-artifact-chip${active}">${escapeHtml(artifact.label)}${escapeHtml(countLabel)}</span>`;
  }).join("");
}

function renderDetailArtifact(payload) {
  const meta = $("#detail-artifact-meta");
  const viewer = $("#detail-artifact-viewer");
  if (!meta || !viewer) return;

  const totalLabel = payload.total_count == null ? "对象" : `${formatNumber(payload.total_count)} 条`;
  const previewLabel = payload.truncated ? "，当前显示前 20 条预览。" : "。";
  meta.textContent = `${payload.artifact.label} · ${totalLabel}${previewLabel}`;
  viewer.textContent = JSON.stringify(payload.content, null, 2);
}

async function loadDetailArtifact(bookId, artifactName) {
  const viewer = $("#detail-artifact-viewer");
  if (viewer) viewer.textContent = "正在加载产物...";
  detailArtifactState.selectedName = artifactName;
  renderDetailArtifactCatalog();
  const payload = await getArtifact(bookId, artifactName);
  if (detailArtifactState.bookId !== bookId) return;
  renderDetailArtifact(payload);
}

async function loadDetailArtifacts(bookId, preferredName = null) {
  detailArtifactState.bookId = bookId;
  if (preferredName) detailArtifactState.selectedName = preferredName;

  const payload = await getArtifacts(bookId);
  if (detailArtifactState.bookId !== bookId) return;

  detailArtifactState.catalog = payload.artifacts || [];
  if (!detailArtifactState.catalog.length) {
    renderDetailArtifactCatalog();
    const meta = $("#detail-artifact-meta");
    const viewer = $("#detail-artifact-viewer");
    if (meta) meta.textContent = "当前还没有可查看的中间产物。";
    if (viewer) viewer.textContent = "等待产物生成...";
    return;
  }

  if (!detailArtifactState.catalog.some((a) => a.name === detailArtifactState.selectedName)) {
    detailArtifactState.selectedName = detailArtifactState.catalog[0].name;
  }
  renderDetailArtifactCatalog();
  await loadDetailArtifact(bookId, detailArtifactState.selectedName);
}

/* ── 全局事件绑定 ── */
function bindGlobalEvents() {
  $("#index-book-btn")?.addEventListener("click", () => rebuildIndex(appState));

  $("#reload-dashboard-btn")?.addEventListener("click", async () => {
    const button = $("#reload-dashboard-btn");
    if (button && button.disabled) return;
    setButtonLoading(button, true, "同步中...");
    setWorkspaceStatus("正在同步看板", "busy");

    try {
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error("同步超时")), 30000);
      });

      const refreshAction = async () => {
        await loadBooks(appState);
        await loadReader(appState, appState.currentChapter);
        await loadDashboard();
        await loadGraph(appState);
      };

      await Promise.race([refreshAction(), timeoutPromise]);
      setWorkspaceStatus("看板已同步", "ready");
    } catch (error) {
      handleActionError(error, "#metric-grid", "看板同步失败");
    } finally {
      setButtonLoading(button, false, "同步中...");
    }
  });

  $("#detail-refresh-graph")?.addEventListener("click", () => {
    if (router.currentBookId) loadDetailGraph(router.currentBookId);
  });

  $("#detail-refresh-artifact")?.addEventListener("click", () => {
    if (router.currentBookId) {
      loadDetailArtifacts(router.currentBookId, detailArtifactState.selectedName)
        .catch((error) => handleActionError(error, "#detail-artifact-summary", "产物加载失败"));
    }
  });

  $("#detail-artifact-select")?.addEventListener("change", (event) => {
    if (router.currentBookId) {
      loadDetailArtifact(router.currentBookId, event.target.value)
        .catch((error) => handleActionError(error, "#detail-artifact-summary", "产物加载失败"));
    }
  });

  $("#detail-graph-density")?.addEventListener("change", () => {
    if (router.currentBookId) loadDetailGraph(router.currentBookId);
  });
}

function initWindowLifecycleShutdown() {
  const sendWindowHeartbeat = () => {
    fetch("/api/system/window-heartbeat", { method: "POST", keepalive: true }).catch(() => {});
  };
  const sendWindowClosed = () => {
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/system/window-closed");
      return;
    }
    fetch("/api/system/window-closed", { method: "POST", keepalive: true }).catch(() => {});
  };

  sendWindowHeartbeat();
  window.setInterval(sendWindowHeartbeat, 3000);
  window.addEventListener("pagehide", sendWindowClosed);
}

/* ── Bootstrap ── */
async function bootstrap() {
  initRouter();
  setTabs();
  initLibrary(appState);
  initReader(appState);
  initGraph(appState);
  initContinuation(appState);
  initEvaluation(appState);
  bindGlobalEvents();
  initWindowLifecycleShutdown();

  try {
    await loadBooks(appState);
    await loadStorageStatsUI();
    await loadTokenStatsUI();
    await loadReader(appState, 1);
    await loadDashboard();
    await loadGraph(appState);
    setWorkspaceStatus("工作区已就绪", "ready");
  } catch (error) {
    handleActionError(error, "#book-cards", "初始化失败");
  }
}

/* ── escapeHtml 用于详情页内部 ── */
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
}

function formatNumber(num) {
  if (!Number.isFinite(num) || num < 0) return "无效";
  if (num === 0) return "0";
  return num.toLocaleString();
}

bootstrap();
