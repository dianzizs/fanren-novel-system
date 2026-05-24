/**
 * 续写台模块 — 约束续写与剧透检测
 */

import { generateContinuation } from "./api.js";
import { $, setWorkspaceStatus, setButtonLoading, setRegionFeedback, handleActionError, currentAskScope } from "./utils.js";
import { loadTokenStatsUI } from "./library.js";

export function initContinuation(appState) {
  bindContinuationEvents(appState);
}

async function doContinueStory(appState) {
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
    const result = await generateContinuation(appState.bookId, payload);
    $("#continuation-result").textContent = result.answer || "暂无结果。";
    setWorkspaceStatus("续写结果已更新", "ready");
    loadTokenStatsUI().catch(console.error);
  } catch (error) {
    handleActionError(error, "#continuation-result", "续写生成失败");
  } finally {
    setButtonLoading(button, false, "生成中...");
  }
}

function bindContinuationEvents(appState) {
  $("#continue-btn")?.addEventListener("click", () => doContinueStory(appState));
}
