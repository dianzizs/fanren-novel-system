/**
 * 阅读台模块 — 章节切换、正文加载、证据问答
 */

import { getReaderPayload, askQuestion } from "./api.js";
import {
  $, $$, escapeHtml, formatMultiline,
  setActiveChapter, setWorkspaceStatus,
  setButtonLoading, setRegionFeedback,
  handleActionError, renderEmptyList, currentAskScope,
} from "./utils.js";
import { loadTokenStatsUI } from "./library.js";

export function initReader(appState) {
  bindReaderEvents(appState);
  loadReader(appState, 1);
}

export async function loadReader(appState, chapter = 1) {
  const payload = await getReaderPayload(appState.bookId, chapter);
  const chapters = payload.chapters || [];
  const current = payload.current_chapter || {};
  const summary = chapters.find((item) => item.chapter === current.chapter)?.summary || "暂无摘要。";
  appState.currentChapter = current.chapter || chapter;

  setActiveChapter(appState.currentChapter, current.title || "");

  $("#reader-summary").innerHTML = `
    <strong>第 ${escapeHtml(appState.currentChapter)} 章 · ${escapeHtml(current.title || "未命名章节")}</strong>
    <p>${escapeHtml(summary)}</p>
  `;

  $("#reader-content").textContent = current.text || "暂无正文。";

  if (!chapters.length) {
    renderEmptyList("#chapter-tree", "暂无章节", "索引完成后，这里会显示章节目录。");
  } else {
    $("#chapter-tree").innerHTML = chapters.map((chapterItem) => `
      <div
        class="chapter-item ${chapterItem.chapter === appState.currentChapter ? "active" : ""}"
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
    const openChapter = () => loadReader(appState, Number(item.dataset.chapter)).catch((error) => {
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

async function doAskQuestion(appState) {
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
    const result = await askQuestion(appState.bookId, payload);

    $("#ask-result").innerHTML = `
      <strong>回答</strong>
      <p>${formatMultiline(result.answer || "暂无回答。")}</p>
      <div class="answer-meta">
        任务类型：${escapeHtml(result.planner?.task_type || "-")} · 置信度：${escapeHtml(result.confidence ?? "-")}
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
    loadTokenStatsUI().catch(console.error);
  } catch (error) {
    handleActionError(error, "#ask-result", "问答生成失败");
  } finally {
    setButtonLoading(button, false, "检索中...");
  }
}

function bindReaderEvents(appState) {
  $("#ask-btn")?.addEventListener("click", () => doAskQuestion(appState));
}
