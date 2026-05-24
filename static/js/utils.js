/**
 * 共享工具函数
 */

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

export { $, $$ };

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[character]));
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "无效";
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export function formatNumber(num) {
  if (!Number.isFinite(num) || num < 0) return "无效";
  if (num === 0) return "0";
  return num.toLocaleString();
}

export function formatMultiline(value) {
  return escapeHtml(value).replace(/\n/g, "<br />");
}

export function feedbackCard(title, message, tone = "neutral") {
  return `
    <div class="feedback-card ${tone}">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

export function setLiveStatus(message) {
  const liveRegion = $("#live-status");
  if (liveRegion) {
    liveRegion.textContent = message;
  }
}

export function setWorkspaceStatus(message, tone = "ready") {
  const status = $("#workspace-status");
  if (status) {
    status.textContent = message;
    status.dataset.tone = tone;
  }
  setLiveStatus(message);
}

export function setHeroBook(title) {
  const target = $("#active-book-name");
  if (target) {
    target.textContent = title || "未命名书目";
  }
}

export function setHeroSubtitle(text) {
  const target = $("#hero-subtitle");
  if (target) {
    target.textContent = text;
  }
}

export function setActiveChapter(chapter, title = "") {
  const target = $("#active-chapter");
  if (!target) return;
  target.textContent = title ? `第 ${chapter} 章 · ${title}` : `第 ${chapter} 章`;
}

export function setScopeSummary(scope) {
  const target = $("#active-scope");
  if (target) {
    target.textContent = `${scope.start} - ${scope.end} 章`;
  }
}

export function setButtonLoading(button, loading, loadingLabel) {
  if (!button) return;
  if (!button.dataset.defaultLabel) {
    button.dataset.defaultLabel = button.textContent.trim();
  }
  button.disabled = loading;
  button.classList.toggle("is-loading", loading);
  button.textContent = loading ? loadingLabel : button.dataset.defaultLabel;
}

export function setRegionFeedback(target, title, message, tone = "neutral") {
  const element = typeof target === "string" ? $(target) : target;
  if (!element) return;
  element.innerHTML = feedbackCard(title, message, tone);
}

export function handleActionError(error, target = null, title = "操作失败") {
  console.error(error);
  const message = error instanceof Error ? error.message : String(error);
  if (target) {
    setRegionFeedback(target, title, message, "error");
  }
  setWorkspaceStatus("发生错误，请查看界面提示", "warn");
}

export function renderEmptyList(target, title, message) {
  const element = typeof target === "string" ? $(target) : target;
  if (!element) return;
  element.innerHTML = feedbackCard(title, message);
}

export function currentAskScope() {
  return {
    start: Number($("#scope-start")?.value || 1),
    end: Number($("#scope-end")?.value || 14),
  };
}
