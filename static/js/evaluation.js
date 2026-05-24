/**
 * 评测模块 — 指标卡片、Baseline 对比、失败案例
 */

import { getDashboard } from "./api.js";
import { $, escapeHtml, formatNumber, feedbackCard, renderEmptyList } from "./utils.js";

export function initEvaluation(appState) {
  loadDashboard();
}

export async function loadDashboard() {
  const dashboard = await getDashboard();
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
