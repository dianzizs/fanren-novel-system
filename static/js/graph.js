/**
 * 知识图谱模块 — Canvas 渲染、力导向布局、节点交互
 */

import { getGraphData } from "./api.js";
import { $, escapeHtml } from "./utils.js";

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

export function initGraph(appState) {
  setupGraphCanvas();
  bindGraphEvents(appState);
}

export async function loadGraph(appState) {
  const scope = currentGraphScope();
  const center = $("#graph-center")?.value || "";
  const params = {
    chapter_start: String(scope.start),
    chapter_end: String(scope.end),
    density: currentGraphDensity(),
  };
  if (center) params.center = center;

  const payload = await getGraphData(appState.bookId, params);
  populateGraphCharacterOptions(payload.available_characters || [], payload.center || center);
  renderGraph(payload);
}

export function resizeGraphCanvas() {
  if (!graphState.canvas || !graphState.ctx) return;

  const rect = graphState.canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  graphState.dpr = dpr;
  graphState.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  graphState.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  graphState.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function currentGraphScope() {
  return {
    start: Number($("#graph-scope-start")?.value || 1),
    end: Number($("#graph-scope-end")?.value || 14),
  };
}

function currentGraphDensity() {
  return $("#graph-density")?.value || "auto";
}

function syncGraphScopeToAsk() {
  const askStart = Number($("#scope-start")?.value || 1);
  const askEnd = Number($("#scope-end")?.value || 14);
  if ($("#graph-scope-start")) $("#graph-scope-start").value = askStart;
  if ($("#graph-scope-end")) $("#graph-scope-end").value = askEnd;
  const scopeTarget = $("#active-scope");
  if (scopeTarget) scopeTarget.textContent = `${askStart} - ${askEnd} 章`;
}

function populateGraphCharacterOptions(characters, selected) {
  const select = $("#graph-center");
  if (!select) return;

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
    if (name === current) option.selected = true;
    select.appendChild(option);
  });
}

function setupGraphCanvas() {
  const canvas = $("#knowledge-graph-canvas");
  if (!canvas) return;

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
  if (node.is_center) return "#2563eb";
  return node.type === "character" ? "#0ea5e9" : "#f59e0b";
}

function edgeColor(edge) {
  if (edge.type === "timeline_next") return "rgba(245, 158, 11, 0.24)";
  if (edge.type === "participates_in") return "rgba(37, 99, 235, 0.26)";
  return "rgba(14, 165, 233, 0.36)";
}

function truncateLabel(label, maxLength = 12) {
  const text = String(label || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function shouldDrawGraphLabel(node, index) {
  const total = graphState.nodes.length;
  if (total <= 35) return true;
  if (graphState.selectedId === node.id || graphState.hoveredId === node.id) return true;
  if (node.is_center) return true;
  if (node.type === "character" && index < 18) return true;
  if (node.type === "event" && index < 8) return true;
  return false;
}

function drawGraph() {
  if (!graphState.ctx || !graphState.canvas) return;

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

  graphState.nodes.forEach((node, index) => {
    const isSelected = graphState.selectedId === node.id;
    const isHovered = graphState.hoveredId === node.id;

    ctx.save();
    ctx.beginPath();
    ctx.fillStyle = graphNodeColor(node);
    ctx.shadowBlur = isSelected ? 18 : isHovered ? 12 : 0;
    ctx.shadowColor = isSelected ? "rgba(37, 99, 235, 0.42)" : "rgba(14, 165, 233, 0.28)";
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.beginPath();
    ctx.lineWidth = isSelected || isHovered ? 3 : 1.5;
    ctx.strokeStyle = isSelected || isHovered ? "#2563eb" : "#cbd5e1";
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.stroke();

    if (shouldDrawGraphLabel(node, index)) {
      ctx.font = node.type === "event"
        ? '600 12px "Noto Sans SC", sans-serif'
        : '600 13px "Noto Sans SC", sans-serif';
      ctx.fillStyle = "#0f172a";
      ctx.textAlign = "center";
      ctx.fillText(truncateLabel(node.label), node.x, node.y + node.radius + 16);
    }
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
    if (Math.sqrt(dx * dx + dy * dy) <= node.radius + 4) return node;
  }
  return null;
}

function onGraphPointerDown(event) {
  if (!graphState.canvas) return;

  const { x, y } = graphPointerPosition(event);
  const node = findGraphNodeAt(x, y);
  if (!node) return;

  graphState.draggedNode = node;
  graphState.selectedId = node.id;
  graphState.pointerOffset = { x: x - node.x, y: y - node.y };
  updateGraphDetail(node);
}

function onGraphPointerMove(event) {
  if (!graphState.canvas) return;

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
  if (!detail) return;

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
    ? `<div class="graph-meta">显示 ${escapeHtml(stats.character_count || 0)}/${escapeHtml(stats.candidate_character_count || stats.character_count || 0)} 人物 · ${escapeHtml(stats.event_count || 0)}/${escapeHtml(stats.candidate_event_count || stats.event_count || 0)} 事件 · 边 ${escapeHtml(stats.edge_count || 0)} · ${escapeHtml(stats.density || "auto")}</div>`
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

function bindGraphEvents(appState) {
  $("#refresh-graph-btn")?.addEventListener("click", () => {
    setGraphStatus("正在刷新图谱", "busy");
    loadGraph(appState)
      .then(() => setGraphStatus("图谱已刷新", "ready"))
      .catch((error) => {
        console.error(error);
        setGraphStatus("图谱加载失败", "warn");
      });
  });

  $("#graph-center")?.addEventListener("change", () => {
    loadGraph(appState).catch(console.error);
  });

  $("#graph-density")?.addEventListener("change", () => {
    loadGraph(appState).catch(console.error);
  });

  $("#scope-start")?.addEventListener("change", syncGraphScopeToAsk);
  $("#scope-end")?.addEventListener("change", syncGraphScopeToAsk);
}

function setGraphStatus(msg, tone) {
  const status = $("#workspace-status");
  if (status) {
    status.textContent = msg;
    status.dataset.tone = tone;
  }
}
