/**
 * 藏书模块 — 书籍列表、导入、删除、索引
 */

import { getBooks, importBook, deleteBook, indexBook, getBookStatus, getStorageStats, getTokenStats } from "./api.js";
import {
  $, $$, escapeHtml, formatBytes, formatNumber,
  setHeroBook, setHeroSubtitle, setWorkspaceStatus,
  setButtonLoading, handleActionError, renderEmptyList, feedbackCard,
} from "./utils.js";

let _booksPollTimer = null;

export function initLibrary(appState) {
  bindLibraryEvents(appState);
  loadBooks(appState);
  loadStorageStatsUI();
  loadTokenStatsUI();
}

export async function loadBooks(appState) {
  const books = await getBooks();
  const bookCards = $("#book-cards");

  if (!books.length) {
    setHeroBook("暂无书目");
    setHeroSubtitle("先导入一本小说，再在这里查看索引、图谱和评测。");
    renderEmptyList(bookCards, "暂无书目", "可以先通过 API 导入一本小说，再回到工作台查看。");
    setWorkspaceStatus("书库为空，等待导入", "idle");
    return;
  }

  const activeBook = books.find((book) => String(book.id) === String(appState.bookId)) || books[0];
  setHeroBook(activeBook.title);
  setHeroSubtitle(
    `已接入 ${activeBook.chapter_count || 0} 章、${activeBook.chunk_count || 0} 个切片，阅读、图谱、续写与评测共用同一套索引。`,
  );

  bookCards.innerHTML = books.map((book) => {
    const isActive = String(book.id) === String(appState.bookId);
    const status = book.status || "pending";
    const primaryAction = status === "pending"
      ? `<button class="start-index-btn secondary" data-book-id="${escapeHtml(book.id)}">开始分析</button>`
      : status === "ready"
      ? `<button class="open-book-btn secondary" data-book-id="${escapeHtml(book.id)}">查看分析</button>`
      : "";
    const statusBadge = status === "indexing"
      ? `<span class="status-tag indexing">分析中 ${Math.round((book.index_progress || 0) * 100)}%</span>`
      : status === "error"
      ? `<span class="status-tag error">分析失败</span>`
      : status === "ready"
      ? `<span class="status-tag ready">已就绪</span>`
      : `<span class="status-tag pending">待分析</span>`;
    const progressBar = status === "indexing"
      ? `<div class="book-progress-bar"><div class="book-progress-fill" style="width:${Math.round((book.index_progress || 0) * 100)}%"></div></div>`
      : "";
    const sourceTag = book.source === "upload"
      ? '<span class="source-tag upload">本地上传</span>'
      : '<span class="source-tag local">原书</span>';
    return `
      <div class="book-card ${isActive ? "active" : ""}">
        <div class="book-card-actions">
          <button class="delete-book-btn" data-book-id="${escapeHtml(book.id)}" data-book-title="${escapeHtml(book.title)}">删除</button>
        </div>
        <div class="status-row">
          ${sourceTag}
          ${statusBadge}
          ${isActive ? "<span class='mini-tag'>当前工作本</span>" : ""}
        </div>
        ${progressBar}
        <h3>${escapeHtml(book.title)}</h3>
        <div class="book-meta">ID：${escapeHtml(book.id)}</div>
        <div class="book-meta">章节数：${escapeHtml(book.chapter_count || "-")}</div>
        <div class="book-meta">切片数：${escapeHtml(book.chunk_count || "-")}</div>
        <div class="book-meta">${escapeHtml(book.source_path || "未记录来源路径")}</div>
        ${primaryAction ? `<div class="book-primary-action">${primaryAction}</div>` : ""}
      </div>
    `;
  }).join("");

  const indexedCount = books.filter((book) => book.indexed).length;
  setWorkspaceStatus(`书库 ${books.length} 本，已索引 ${indexedCount} 本`, indexedCount ? "ready" : "idle");

  const indexingBooks = books.filter((b) => b.status === "indexing");
  if (indexingBooks.length > 0) {
    clearTimeout(_booksPollTimer);
    _booksPollTimer = setTimeout(() => loadBooks(appState), 2000);
  }
}

async function loadStorageStatsUI() {
  try {
    const stats = await getStorageStats();
    $("#index-size").textContent = formatBytes(stats.total_index_size || 0);
    $("#uploads-size").textContent = formatBytes(stats.total_uploads_size || 0);
  } catch (error) {
    console.error("Failed to load storage stats:", error);
    $("#index-size").textContent = "加载失败";
    $("#uploads-size").textContent = "加载失败";
  }
}

async function loadTokenStatsUI() {
  try {
    const stats = await getTokenStats();
    $("#token-total").textContent = formatNumber(stats.total_tokens || 0);
  } catch (error) {
    console.error("Failed to load token stats:", error);
    $("#token-total").textContent = "加载失败";
  }
}

function showDeleteConfirmDialog(bookId, bookTitle, appState) {
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
      await deleteBook(btn.dataset.bookId);
      overlay.remove();
      await loadBooks(appState);
      await loadStorageStatsUI();
      setWorkspaceStatus("书目已删除", "ready");
    } catch (error) {
      if (error.message.includes("indexing") || error.message.includes("409")) {
        alert("Cannot delete book while indexing");
      } else {
        handleActionError(error, null, "删除失败");
      }
      btn.disabled = false;
      btn.textContent = "确认删除";
    }
  });
}

export async function startBookIndex(bookId, appState) {
  const btn = document.querySelector(`.start-index-btn[data-book-id="${bookId}"]`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = "启动中...";
  }
  try {
    const result = await indexBook(bookId);
    if (result.status === "indexing" || result.status === "ready") {
      appState.navigate(`#/book/${bookId}`);
    }
  } catch (error) {
    handleActionError(error, "#book-cards", "启动失败");
  }
}

export async function rebuildIndex(appState) {
  const button = $("#index-book-btn");
  if (button && button.disabled) return;
  setButtonLoading(button, true, "构建中...");
  setWorkspaceStatus("正在重建索引", "busy");

  const currentPollBookId = appState.bookId;

  try {
    await indexBook(currentPollBookId, true);

    const pollStart = Date.now();
    const timeout = 30 * 60 * 1000;

    const poll = async () => {
      if (appState.bookId !== currentPollBookId) {
        setButtonLoading(button, false, "构建中...");
        return;
      }
      if (Date.now() - pollStart > timeout) {
        handleActionError(new Error("重建索引超时"), "#book-cards", "超时提示");
        setWorkspaceStatus("重建索引超时", "error");
        setButtonLoading(button, false, "构建中...");
        return;
      }

      try {
        const result = await getBookStatus(currentPollBookId);
        if (result.status === "ready") {
          await loadBooks(appState);
          if (appState.onIndexComplete) await appState.onIndexComplete();
          setWorkspaceStatus("索引已重建", "ready");
          setButtonLoading(button, false, "构建中...");
        } else if (result.status === "error") {
          handleActionError(new Error(result.message || "重建失败"), "#book-cards", "重建错误");
          setWorkspaceStatus("重建索引失败", "error");
          setButtonLoading(button, false, "构建中...");
        } else {
          let pct = (result.progress * 100).toFixed(0);
          setWorkspaceStatus(`正在重建索引 (${pct}%)`, "busy");
          setTimeout(poll, 2000);
        }
      } catch (error) {
        console.error("Polling error:", error);
        setTimeout(poll, 2000);
      }
    };

    poll();
  } catch (error) {
    handleActionError(error, "#book-cards", "索引重建失败");
    setButtonLoading(button, false, "构建中...");
    setWorkspaceStatus("索引重建失败", "error");
  }
}

function bindLibraryEvents(appState) {
  document.addEventListener("click", (e) => {
    if (e.target.classList.contains("delete-book-btn")) {
      showDeleteConfirmDialog(e.target.dataset.bookId, e.target.dataset.bookTitle, appState);
    }
    if (e.target.classList.contains("start-index-btn")) {
      startBookIndex(e.target.dataset.bookId, appState);
    }
    if (e.target.classList.contains("open-book-btn")) {
      appState.navigate(`#/book/${e.target.dataset.bookId}`);
    }
  });

  $("#refresh-books-btn")?.addEventListener("click", async () => {
    const btn = $("#refresh-books-btn");
    setButtonLoading(btn, true, "刷新中...");
    try {
      await loadBooks(appState);
      await loadStorageStatsUI();
      setWorkspaceStatus("书库已刷新", "ready");
    } catch (error) {
      handleActionError(error, "#book-cards", "刷新失败");
    } finally {
      setButtonLoading(btn, false, "刷新中...");
    }
  });

  // 创建并重用一个隐藏的 input
  let fileInput = document.getElementById("hidden-import-input");
  if (!fileInput) {
    fileInput = document.createElement("input");
    fileInput.id = "hidden-import-input";
    fileInput.type = "file";
    fileInput.accept = ".txt";
    fileInput.style.display = "none";
    document.body.appendChild(fileInput);

    fileInput.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const formData = new FormData();
      formData.append("file", file);
      try {
        await importBook(formData);
        await loadBooks(appState);
        await loadStorageStatsUI();
        setWorkspaceStatus("新书已导入", "ready");
      } catch (error) {
        handleActionError(error, "#book-cards", "导入失败");
      } finally {
        // 重置 input，允许重复选择同一个文件
        e.target.value = "";
      }
    });
  }

  $("#import-book-btn")?.addEventListener("click", () => {
    fileInput.click();
  });
}

export { loadStorageStatsUI, loadTokenStatsUI };
